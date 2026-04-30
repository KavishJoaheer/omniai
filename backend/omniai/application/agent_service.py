from __future__ import annotations

import json
from dataclasses import dataclass, field

from pydantic import BaseModel, Field

from omniai.application.retrieval_service import RetrievalRequest, RetrievalService
from omniai.domain.agents.models import Agent, AgentRun
from omniai.domain.knowledge.models import utc_now
from omniai.ports.agents import AgentStorePort
from omniai.ports.sandbox import SandboxPort, SandboxRequest


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


@dataclass(slots=True)
class AgentService:
    store: AgentStorePort
    retrieval_service: RetrievalService
    sandbox: SandboxPort | None = field(default=None)

    def list_agents(self) -> list[Agent]:
        return self.store.list_agents()

    def create_agent(self, payload: CreateAgentInput) -> Agent:
        return self.store.create_agent(
            name=payload.name,
            description=payload.description,
            definition=_normalize_definition(payload.definition),
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

    async def _execute_run(self, agent: Agent, run: AgentRun) -> AgentRun:
        definition = _normalize_definition(agent.definition)
        input_text = str(run.input.get("input") or "").strip()
        events: list[dict] = []
        context: dict = {"input": input_text, "references": [], "messages": [], "answer": "", "usage": {}}
        self.store.update_run(
            run_id=run.id,
            status="RUNNING",
            output={},
            events=events,
            started=True,
        )

        try:
            for node in _walk_graph(definition):
                node_id = str(node.get("id") or node.get("type") or "node")
                _append_event(events, "node.start", node_id, {"type": node.get("type"), "label": node.get("label")})
                node_output = await self._execute_node(node, definition, context)
                _append_event(events, "node.output", node_id, node_output)

            answer = str(context.get("answer") or "") or _compose_answer(definition, input_text, context.get("references", []))
            output = {
                "answer": answer,
                "references": context.get("references", []),
                "messages": context.get("messages", []),
                "usage": context.get("usage") or _estimate_usage(input_text, answer),
            }
            return self.store.update_run(
                run_id=run.id,
                status="COMPLETED",
                output=output,
                events=events,
                completed=True,
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

    async def _execute_node(self, node: dict, definition: dict, context: dict) -> dict:
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

        raise ValueError(f"Unsupported agent node type: {node_type}.")


    async def _execute_code_node(self, config: dict, context: dict) -> dict:
        """Run a Python code node inside the configured sandbox.

        The agent context is injected as module-level variables so code can
        reference ``user_input`` and ``context_text`` without boilerplate.
        stdout of the script replaces ``context["answer"]`` so downstream
        message/end nodes surface the result automatically.
        """
        code = str(config.get("code") or "").strip()
        timeout = float(config.get("timeout_seconds") or 10.0)

        if not code:
            return {"stdout": "", "stderr": "no code configured", "exit_code": 0, "skipped": True}

        if self.sandbox is None:
            return {
                "stdout": "",
                "stderr": "sandbox disabled — set SANDBOX_KIND=subprocess to enable code nodes",
                "exit_code": 1,
                "skipped": True,
            }

        # Inject retrieval context so code can use it without extra HTTP calls.
        context_text = "\n".join(
            str(r.get("snippet") or r.get("text") or "") for r in context.get("references", [])
        )
        user_input = str(context.get("input") or "")
        preamble = (
            f"user_input = {user_input!r}\n"
            f"context_text = {context_text!r}\n"
            "# --- agent code node ---\n"
        )
        full_code = preamble + code

        result = await self.sandbox.run(
            SandboxRequest(code=full_code, timeout_seconds=timeout)
        )

        # Promote stdout to the answer so downstream nodes receive it.
        if result.stdout.strip():
            context["answer"] = result.stdout.strip()

        return {
            "stdout": result.stdout,
            "stderr": result.stderr,
            "exit_code": result.exit_code,
            "timed_out": result.timed_out,
            "artifacts": list(result.artifacts.keys()),
        }


def _normalize_definition(definition: dict | None) -> dict:
    normalized = json.loads(json.dumps(DEFAULT_AGENT_DEFINITION))
    normalized.update(definition or {})
    normalized["collectionIds"] = list(dict.fromkeys(normalized.get("collectionIds") or []))
    normalized["retrieval"] = {**DEFAULT_AGENT_DEFINITION["retrieval"], **(normalized.get("retrieval") or {})}
    normalized["generation"] = {**DEFAULT_AGENT_DEFINITION["generation"], **(normalized.get("generation") or {})}
    return normalized


def _walk_graph(definition: dict) -> list[dict]:
    nodes = list(definition.get("nodes") or DEFAULT_AGENT_DEFINITION["nodes"])
    edges = list(definition.get("edges") or DEFAULT_AGENT_DEFINITION["edges"])
    by_id = {str(node.get("id")): node for node in nodes if node.get("id")}
    current = next((node for node in nodes if node.get("type") == "start"), nodes[0])
    visited: set[str] = set()
    ordered: list[dict] = []
    for _ in range(50):
        node_id = str(current.get("id") or "")
        if not node_id:
            raise ValueError("Agent node is missing an id.")
        if node_id in visited:
            raise ValueError("Agent graph contains a cycle in the executable path.")
        visited.add(node_id)
        ordered.append(current)
        if current.get("type") == "end":
            return ordered
        next_id = next((str(edge.get("to")) for edge in edges if edge.get("from") == node_id), "")
        if not next_id:
            return ordered
        if next_id not in by_id:
            raise ValueError(f"Agent edge points to missing node: {next_id}.")
        current = by_id[next_id]
    raise ValueError("Agent graph exceeded the maximum executable step count.")


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
