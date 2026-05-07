from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass, field

from pydantic import BaseModel, Field

from omniai.application.retrieval_service import RetrievalRequest, RetrievalService
from omniai.domain.agents.models import Agent, AgentRun
from omniai.domain.knowledge.models import utc_now
from omniai.ports.agents import AgentStorePort
from omniai.ports.sandbox import SandboxPort, SandboxRequest

logger = logging.getLogger(__name__)


DEFAULT_AGENT_DEFINITION = {
    "version": 1,
    "nodes": [
        {"id": "start", "type": "start", "label": "Start"},
        {"id": "retrieval", "type": "retrieval", "label": "Retrieve"},
        {"id": "generate", "type": "generate", "label": "Generate"},
        {"id": "message", "type": "message", "label": "Message", "config": {"template": "{answer}"}},
        {"id": "end", "type": "end", "label": "End"},
    ],
    "edges": [
        {"from": "start", "to": "retrieval"},
        {"from": "retrieval", "to": "generate"},
        {"from": "generate", "to": "message"},
        {"from": "message", "to": "end"},
    ],
    "collectionIds": [],
    "retrieval": {"topK": 5, "vectorWeight": 0.65, "similarityThreshold": 0.0},
    "generation": {
        "mode": "local-grounded",
        "fallbackText": "I could not find a grounded answer in the knowledge base.",
    },
}

# Token costs in USD per 1000 tokens (approximate for cost-alerting estimates)
_COST_PER_1K_TOKENS = 0.002


class _PausedError(Exception):
    """Sentinel: raised when a human_input node suspends the run."""
    def __init__(self, node_id: str, prompt: str) -> None:
        self.node_id = node_id
        self.prompt = prompt
        super().__init__(f"Run paused at node {node_id!r}")


class CreateAgentInput(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    description: str | None = Field(default=None, max_length=2000)
    definition: dict = Field(default_factory=lambda: json.loads(json.dumps(DEFAULT_AGENT_DEFINITION)))


class UpdateAgentInput(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=128)
    description: str | None = Field(default=None, max_length=2000)
    definition: dict | None = None
    published: bool | None = None


class StartAgentRunInput(BaseModel):
    input: str = Field(min_length=1, max_length=12000)
    variables: dict = Field(default_factory=dict)


class ResumeAgentRunInput(BaseModel):
    """Payload for resuming a PAUSED run (human-in-the-loop)."""
    human_input: str = Field(min_length=1, max_length=12000)
    approved: bool = True


class ReplayAgentRunInput(BaseModel):
    """Replay an existing run, optionally fast-forwarding to a specific event."""
    from_event: int = Field(default=0, ge=0,
                            description="Re-execute from this event index (0 = full replay)")
    input_override: str | None = Field(default=None, max_length=12000,
                                       description="Override the original run's input text")


@dataclass(slots=True)
class AgentService:
    store: AgentStorePort
    retrieval_service: RetrievalService
    sandbox: SandboxPort | None = field(default=None)
    cost_alert_usd: float = field(default=0.0)

    def list_agents(self) -> list[Agent]:
        return self.store.list_agents()

    def create_agent(self, payload: CreateAgentInput, *, template_id: str | None = None) -> Agent:
        return self.store.create_agent(
            name=payload.name,
            description=payload.description,
            definition=_normalize_definition(payload.definition),
            template_id=template_id,
        )

    def get_agent(self, agent_id: str) -> Agent:
        return self.store.get_agent(agent_id)

    def update_agent(self, agent_id: str, payload: UpdateAgentInput) -> Agent:
        return self.store.update_agent(
            agent_id=agent_id,
            name=payload.name,
            description=payload.description,
            definition=_normalize_definition(payload.definition) if payload.definition is not None else None,
            published=payload.published,
        )

    def delete_agent(self, agent_id: str) -> dict:
        self.store.delete_agent(agent_id)
        return {"id": agent_id, "deleted": True}

    def publish_agent(self, agent_id: str) -> Agent:
        return self.store.update_agent(agent_id=agent_id, published=True)

    def list_runs(self, agent_id: str) -> list[AgentRun]:
        return self.store.list_runs(agent_id)

    def get_run(self, agent_id: str, run_id: str) -> AgentRun:
        return self.store.get_run(agent_id, run_id)

    async def start_run(self, agent_id: str, payload: StartAgentRunInput) -> AgentRun:
        agent = self.store.get_agent(agent_id)
        run = self.store.create_run(
            agent_id=agent.id,
            input_payload={"input": payload.input.strip(), "variables": payload.variables},
        )
        return await self._execute_run(agent, run)

    # ── M20: human-in-the-loop resume ─────────────────────────────────────────

    async def resume_run(
        self,
        agent_id: str,
        run_id: str,
        payload: ResumeAgentRunInput,
    ) -> AgentRun:
        """Resume a PAUSED run with human-provided input.

        The human's answer is injected into the execution context, and the run
        continues from the node *after* the human_input node.
        """
        agent = self.store.get_agent(agent_id)
        run = self.store.get_run(agent_id, run_id)
        if run.status != "PAUSED":
            raise ValueError(f"Run {run_id!r} is not paused (status={run.status!r}).")

        # Rebuild context from the run's existing events
        input_text = str(run.input.get("input") or "").strip()
        context: dict = {
            "input": input_text,
            "references": [],
            "messages": [],
            "answer": "",
            "usage": {},
            # Inject human's response so downstream nodes can use it
            "human_input": payload.human_input,
            "human_approved": payload.approved,
        }
        _replay_context_from_events(context, run.events)

        events = list(run.events)
        paused_node_id = run.paused_at_node or ""
        _append_event(events, "run.resumed", paused_node_id,
                      {"human_input": payload.human_input, "approved": payload.approved})

        definition = _normalize_definition(agent.definition)
        return await self._execute_from_node(
            agent=agent,
            run=run,
            definition=definition,
            context=context,
            events=events,
            start_after_node_id=paused_node_id,
        )

    # ── M20: time-travel replay ───────────────────────────────────────────────

    async def replay_run(
        self,
        agent_id: str,
        run_id: str,
        payload: ReplayAgentRunInput,
    ) -> AgentRun:
        """Create a new run that replays (and optionally fast-forwards) an existing one.

        Events 0..from_event are replayed from the stored event log without
        re-executing them.  Execution then continues live from that point.

        This enables "time travel" debugging: branch from any past event and
        see how the run would have gone with different inputs or configurations.
        """
        original = self.store.get_run(agent_id, run_id)
        agent = self.store.get_agent(agent_id)

        input_text = (payload.input_override or "").strip() or str(original.input.get("input") or "").strip()

        # Create a new run linked to the original
        new_run = self.store.create_run(
            agent_id=agent_id,
            input_payload={"input": input_text, "variables": {}},
            replay_of_run_id=run_id,
            replay_from_event=payload.from_event,
        )

        # Replay stored events up to the requested offset
        replay_events = list(original.events[: payload.from_event])
        context: dict = {"input": input_text, "references": [], "messages": [], "answer": "", "usage": {}}
        _replay_context_from_events(context, replay_events)

        if replay_events:
            _append_event(replay_events, "run.replay_start", "runtime",
                          {"replayed_from_run": run_id, "from_event": payload.from_event})

        # Find which node to resume execution from
        start_after_node_id: str | None = None
        if replay_events:
            # Find the last node.output event to determine where to continue
            for evt in reversed(replay_events):
                if evt.get("event") == "node.output":
                    start_after_node_id = str(evt.get("nodeId") or "")
                    break

        return await self._execute_from_node(
            agent=agent,
            run=new_run,
            definition=_normalize_definition(agent.definition),
            context=context,
            events=replay_events,
            start_after_node_id=start_after_node_id,
        )

    # ── Core execution engine ─────────────────────────────────────────────────

    async def _execute_run(self, agent: Agent, run: AgentRun) -> AgentRun:
        definition = _normalize_definition(agent.definition)
        input_text = str(run.input.get("input") or "").strip()
        events: list[dict] = []
        context: dict = {"input": input_text, "references": [], "messages": [], "answer": "", "usage": {}}
        return await self._execute_from_node(
            agent=agent,
            run=run,
            definition=definition,
            context=context,
            events=events,
            start_after_node_id=None,
        )

    async def _execute_from_node(
        self,
        *,
        agent: Agent,
        run: AgentRun,
        definition: dict,
        context: dict,
        events: list[dict],
        start_after_node_id: str | None,
    ) -> AgentRun:
        """Execute the graph from (optionally) a specific node.

        If ``start_after_node_id`` is provided, nodes up to and including that
        node are skipped; execution begins at the next node.
        """
        input_text = str(context.get("input") or "").strip()

        self.store.update_run(
            run_id=run.id,
            status="RUNNING",
            output={},
            events=events,
            started=True,
        )

        try:
            # Build the ordered execution plan (supports fan-out/join)
            plan = _build_execution_plan(definition)

            # Skip nodes up to start_after_node_id if requested
            skip_until: str | None = start_after_node_id
            skipping = skip_until is not None

            for step in plan:
                if isinstance(step, list):
                    # Parallel branches — list[list[dict]]
                    branches = step
                    if skipping:
                        # Check if any branch contains the target node
                        for branch in branches:
                            for node in branch:
                                if str(node.get("id")) == skip_until:
                                    skipping = False
                                    break
                        if skipping:
                            continue  # Skip the entire fan-out/join group
                    branch_contexts = await asyncio.gather(*[
                        self._run_branch(branch, definition, dict(context))
                        for branch in branches
                    ])
                    # Merge branch results: combine references, keep last non-empty answer
                    merged_refs: list[dict] = []
                    for bc in branch_contexts:
                        merged_refs.extend(bc.get("references") or [])
                        if bc.get("answer"):
                            context["answer"] = bc["answer"]
                    # Re-index merged references
                    for idx, ref in enumerate(merged_refs, start=1):
                        ref["index"] = idx
                        ref["label"] = f"[{idx}]"
                    context["references"] = merged_refs
                    _append_event(events, "node.parallel_merge", "join",
                                  {"branch_count": len(branches), "reference_count": len(merged_refs)})
                else:
                    # Single node
                    node = step
                    node_id = str(node.get("id") or node.get("type") or "node")

                    if skipping:
                        if node_id == skip_until:
                            skipping = False
                        continue

                    node_type = str(node.get("type") or "").lower()
                    if node_type in ("fan_out", "join"):
                        # Handled at plan level; skip as individual steps
                        continue

                    _append_event(events, "node.start", node_id,
                                  {"type": node.get("type"), "label": node.get("label")})
                    node_output = await self._execute_node(node, definition, context, run_id=run.id)
                    _append_event(events, "node.output", node_id, node_output)

        except _PausedError as pause:
            # Human-in-the-loop: persist paused state and return
            return self.store.update_run(
                run_id=run.id,
                status="PAUSED",
                output={"paused_at_node": pause.node_id, "pause_prompt": pause.prompt},
                events=events,
                paused_at_node=pause.node_id,
            )
        except Exception as exc:
            _append_event(events, "node.error", "runtime", {"error": str(exc)})
            return self.store.update_run(
                run_id=run.id,
                status="FAILED",
                output={"error": str(exc)},
                events=events,
                error_message=str(exc),
                completed=True,
            )

        answer = (str(context.get("answer") or "")
                  or _compose_answer(definition, input_text, context.get("references", [])))
        usage = context.get("usage") or _estimate_usage(input_text, answer)
        cost_usd = _compute_cost_usd(usage)

        # Cost alerting
        if self.cost_alert_usd > 0 and cost_usd >= self.cost_alert_usd:
            logger.warning(
                "agent_run cost alert: run=%s agent=%s cost_usd=%.4f threshold=%.4f",
                run.id, agent.id, cost_usd, self.cost_alert_usd,
            )
            _append_event(events, "run.cost_alert", "runtime",
                          {"cost_usd": cost_usd, "threshold_usd": self.cost_alert_usd})

        output = {
            "answer": answer,
            "references": context.get("references", []),
            "messages": context.get("messages", []),
            "usage": usage,
            "cost_usd": cost_usd,
        }
        return self.store.update_run(
            run_id=run.id,
            status="COMPLETED",
            output=output,
            events=events,
            cost_usd=cost_usd,
            completed=True,
        )

    async def _run_branch(
        self,
        branch_nodes: list[dict],
        definition: dict,
        context: dict,
    ) -> dict:
        """Execute a single parallel branch and return its context."""
        for node in branch_nodes:
            node_type = str(node.get("type") or "").lower()
            if node_type in ("fan_out", "join"):
                continue
            try:
                await self._execute_node(node, definition, context)
            except _PausedError:
                break  # Can't pause inside a parallel branch — skip
            except Exception as exc:
                logger.warning("branch node %r failed: %s", node.get("id"), exc)
                break
        return context

    async def _execute_node(
        self,
        node: dict,
        definition: dict,
        context: dict,
        run_id: str = "",
    ) -> dict:
        node_type = str(node.get("type") or "").lower()
        config = dict(node.get("config") or {})
        user_input = str(context.get("input") or "")

        if node_type == "start":
            return {"text": user_input}

        if node_type == "retrieval":
            retrieval_config = {**(definition.get("retrieval") or {}), **config}
            response = await self.retrieval_service.retrieve(
                RetrievalRequest(
                    query=user_input,
                    collection_ids=retrieval_config.get("collectionIds") or definition.get("collectionIds", []),
                    top_k=int(retrieval_config.get("topK", 5)),
                    vector_weight=float(retrieval_config.get("vectorWeight", 0.65)),
                )
            )
            references = [_hit_to_reference(index, hit) for index, hit in enumerate(response.hits, start=1)]
            context["references"] = references
            return {"resultCount": len(references), "references": references}

        if node_type == "generate":
            answer = _compose_answer(definition, user_input, context.get("references", []), node=node)
            context["answer"] = answer
            context["usage"] = _estimate_usage(user_input, answer)
            return {"answer": answer, "references": context.get("references", [])}

        if node_type == "message":
            message = _render_template(str(config.get("template") or node.get("message") or "{answer}"), context)
            context["messages"] = [*list(context.get("messages") or []), {"nodeId": node.get("id"), "content": message}]
            if not context.get("answer"):
                context["answer"] = message
            return {"message": message}

        if node_type == "end":
            return {"answer": context.get("answer", ""), "references": context.get("references", [])}

        if node_type == "code":
            return await self._execute_code_node(config, context)

        # M20: human-in-the-loop
        if node_type == "human_input":
            prompt = str(config.get("prompt") or "Human review requested.")
            node_id = str(node.get("id") or "human_input")
            # If a human_input was already supplied (resume path), consume it
            if context.get("human_input"):
                human_response = str(context.pop("human_input"))
                context["answer"] = human_response
                return {"human_input_received": human_response, "approved": context.pop("human_approved", True)}
            # Otherwise pause
            raise _PausedError(node_id=node_id, prompt=prompt)

        # M20: fan_out / join handled at plan level — skip if encountered directly
        if node_type in ("fan_out", "join"):
            return {}

        raise ValueError(f"Unsupported agent node type: {node_type!r}.")

    async def _execute_code_node(self, config: dict, context: dict) -> dict:
        """Run a Python/JavaScript/Bash code node inside the configured sandbox."""
        code = str(config.get("code") or "").strip()
        timeout = float(config.get("timeout_seconds") or 10.0)
        language = str(config.get("language") or "python").lower()

        if not code:
            return {"stdout": "", "stderr": "no code configured", "exit_code": 0, "skipped": True}

        if self.sandbox is None:
            return {
                "stdout": "",
                "stderr": "sandbox disabled — set SANDBOX_KIND=subprocess to enable code nodes",
                "exit_code": 1,
                "skipped": True,
            }

        # Inject retrieval context
        context_text = "\n".join(
            str(r.get("snippet") or r.get("text") or "") for r in context.get("references", [])
        )
        user_input = str(context.get("input") or "")

        if language == "python":
            preamble = (
                f"user_input = {user_input!r}\n"
                f"context_text = {context_text!r}\n"
                "# --- agent code node ---\n"
            )
            full_code = preamble + code
        elif language == "javascript":
            preamble = (
                f"const user_input = {json.dumps(user_input)};\n"
                f"const context_text = {json.dumps(context_text)};\n"
                "// --- agent code node ---\n"
            )
            full_code = preamble + code
        elif language == "bash":
            preamble = (
                f'USER_INPUT={json.dumps(user_input)}\n'
                f'CONTEXT_TEXT={json.dumps(context_text)}\n'
                "# --- agent code node ---\n"
            )
            full_code = preamble + code
        else:
            full_code = code

        result = await self.sandbox.run(
            SandboxRequest(code=full_code, language=language, timeout_seconds=timeout)
        )

        if result.stdout.strip():
            context["answer"] = result.stdout.strip()

        return {
            "stdout": result.stdout,
            "stderr": result.stderr,
            "exit_code": result.exit_code,
            "timed_out": result.timed_out,
            "artifacts": list(result.artifacts.keys()),
        }


# ── Helpers ───────────────────────────────────────────────────────────────────

def _normalize_definition(definition: dict | None) -> dict:
    normalized = json.loads(json.dumps(DEFAULT_AGENT_DEFINITION))
    normalized.update(definition or {})
    normalized["collectionIds"] = list(dict.fromkeys(normalized.get("collectionIds") or []))
    normalized["retrieval"] = {**DEFAULT_AGENT_DEFINITION["retrieval"], **(normalized.get("retrieval") or {})}
    normalized["generation"] = {**DEFAULT_AGENT_DEFINITION["generation"], **(normalized.get("generation") or {})}
    return normalized


def _build_execution_plan(definition: dict) -> list:
    """Build an ordered execution plan that supports fan-out/join parallelism.

    Returns a list where each item is either:
    - A single node dict (sequential step), or
    - A list[list[dict]] representing parallel branches (fan-out/join group).
    """
    nodes = list(definition.get("nodes") or DEFAULT_AGENT_DEFINITION["nodes"])
    edges = list(definition.get("edges") or DEFAULT_AGENT_DEFINITION["edges"])
    by_id: dict[str, dict] = {str(n.get("id")): n for n in nodes if n.get("id")}

    # Build adjacency
    out_edges: dict[str, list[str]] = {}
    in_degree: dict[str, int] = {str(n.get("id")): 0 for n in nodes if n.get("id")}
    for e in edges:
        src, dst = str(e.get("from") or ""), str(e.get("to") or "")
        out_edges.setdefault(src, []).append(dst)
        if dst in in_degree:
            in_degree[dst] += 1

    current = next((n for n in nodes if n.get("type") == "start"), nodes[0] if nodes else None)
    if current is None:
        return []

    plan: list = []
    visited: set[str] = set()

    def walk_linear(start_node: dict) -> None:
        node = start_node
        for _ in range(200):
            node_id = str(node.get("id") or "")
            if node_id in visited:
                return
            visited.add(node_id)
            node_type = str(node.get("type") or "").lower()

            successors = out_edges.get(node_id, [])

            if node_type == "fan_out" or (len(successors) > 1):
                # Fan-out: collect branches up to the join node
                plan.append(node)  # the fan_out node itself
                branches: list[list[dict]] = []
                join_node: dict | None = None

                # Collect each branch's nodes until we hit join
                for succ_id in successors:
                    branch: list[dict] = []
                    curr = by_id.get(succ_id)
                    for _ in range(50):
                        if curr is None:
                            break
                        curr_type = str(curr.get("type") or "").lower()
                        if curr_type == "join" or in_degree.get(str(curr.get("id")), 0) > 1:
                            join_node = curr
                            break
                        branch.append(curr)
                        next_ids = out_edges.get(str(curr.get("id")), [])
                        curr = by_id.get(next_ids[0]) if next_ids else None
                    branches.append(branch)

                if branches:
                    plan.append(branches)  # parallel group

                if join_node is not None:
                    jid = str(join_node.get("id") or "")
                    if jid not in visited:
                        visited.add(jid)
                        plan.append(join_node)
                        # Continue from join's successors
                        join_succs = out_edges.get(jid, [])
                        if join_succs:
                            next_node = by_id.get(join_succs[0])
                            if next_node:
                                node = next_node
                                continue
                return

            # Sequential node
            plan.append(node)
            if node_type == "end":
                return

            if successors:
                next_node = by_id.get(successors[0])
                if next_node is None:
                    return
                node = next_node
            else:
                return
        raise ValueError("Agent graph exceeded the maximum executable step count.")

    walk_linear(current)
    return plan


def _walk_graph(definition: dict) -> list[dict]:
    """Legacy linear graph walker (kept for backward compat)."""
    plan = _build_execution_plan(definition)
    # Flatten: skip parallel groups (list items)
    result: list[dict] = []
    for step in plan:
        if isinstance(step, list):
            for branch in step:
                result.extend(branch)
        elif isinstance(step, dict):
            result.append(step)
    return result


def _replay_context_from_events(context: dict, events: list[dict]) -> None:
    """Reconstruct context fields from a stored event log."""
    for evt in events:
        if evt.get("event") != "node.output":
            continue
        data = evt.get("data") or {}
        if "references" in data:
            context["references"] = data["references"]
        if "answer" in data:
            context["answer"] = data["answer"]
        if "message" in data:
            existing = list(context.get("messages") or [])
            existing.append({"nodeId": evt.get("nodeId"), "content": data["message"]})
            context["messages"] = existing


def _compute_cost_usd(usage: dict) -> float:
    """Estimate run cost from token usage (approximate)."""
    total_tokens = (usage.get("prompt_tokens") or 0) + (usage.get("completion_tokens") or 0)
    return round(total_tokens / 1000 * _COST_PER_1K_TOKENS, 6)


def _hit_to_reference(index: int, hit) -> dict:
    metadata = hit.metadata or {}
    return {
        "index": index,
        "label": f"[{index}]",
        "chunkId": hit.chunk_id,
        "collectionId": hit.collection_id,
        "documentId": hit.document_id,
        "documentName": str(metadata.get("document_name") or metadata.get("filename") or "Unknown"),
        "score": hit.score,
        "snippet": hit.snippet or hit.text[:280],
    }


def _compose_answer(definition: dict, user_input: str, references: list[dict], *, node: dict | None = None) -> str:
    del user_input
    generation = {**(definition.get("generation", {}) or {}), **((node or {}).get("config", {}) or {})}
    if not references:
        return str(generation.get("fallbackText") or "I could not find a grounded answer in the knowledge base.")
    lines = ["Agent result:"]
    for reference in references:
        snippet = " ".join(str(reference.get("snippet") or "").split())
        if len(snippet) > 240:
            snippet = f"{snippet[:237].rstrip()}..."
        lines.append(f"{reference.get('documentName', 'Document')}: {snippet} {reference.get('label', '')}")
    return "\n\n".join(lines)


def _render_template(template: str, context: dict) -> str:
    return template.replace("{input}", str(context.get("input") or "")).replace(
        "{answer}", str(context.get("answer") or "")
    )


def _estimate_usage(prompt_text: str, completion_text: str) -> dict[str, int]:
    from omniai.utils.token_counter import estimate_usage
    return estimate_usage(prompt_text, completion_text)


def _append_event(events: list[dict], event: str, node_id: str, data: dict) -> None:
    events.append({"event": event, "nodeId": node_id, "data": data, "createdAt": utc_now().isoformat()})
