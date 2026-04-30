import { FormEvent, useEffect, useMemo, useState } from "react";

import { Agent, AgentRun, ApiError, Collection, api } from "../../api/client";

type AgentNode = NonNullable<Agent["definition"]["nodes"]>[number];
type AgentNodeType = "start" | "retrieval" | "generate" | "message" | "code" | "end";

const ADDABLE_NODE_TYPES: Array<{ label: string; type: AgentNodeType }> = [
  { label: "Retrieval", type: "retrieval" },
  { label: "Generate", type: "generate" },
  { label: "Message", type: "message" },
  { label: "Code (Sandbox)", type: "code" }
];

const DEFAULT_FALLBACK = "I could not find a grounded answer in the knowledge base.";

export function AgentsPage() {
  const [agents, setAgents] = useState<Agent[]>([]);
  const [runs, setRuns] = useState<AgentRun[]>([]);
  const [collections, setCollections] = useState<Collection[]>([]);
  const [agentId, setAgentId] = useState("");
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [selectedCollections, setSelectedCollections] = useState<string[]>([]);
  const [editName, setEditName] = useState("");
  const [editDescription, setEditDescription] = useState("");
  const [editCollections, setEditCollections] = useState<string[]>([]);
  const [editTopK, setEditTopK] = useState(5);
  const [editVectorWeight, setEditVectorWeight] = useState(0.65);
  const [editThreshold, setEditThreshold] = useState(0);
  const [editFallback, setEditFallback] = useState(DEFAULT_FALLBACK);
  const [builderNodes, setBuilderNodes] = useState<AgentNode[]>(defaultNodes());
  const [selectedNodeId, setSelectedNodeId] = useState("retrieval");
  const [newNodeType, setNewNodeType] = useState<AgentNodeType>("message");
  const [runInput, setRunInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");

  const selectedAgent = useMemo(
    () => agents.find((agent) => agent.id === agentId) || null,
    [agents, agentId]
  );
  const selectedNode = useMemo(
    () => builderNodes.find((node) => node.id === selectedNodeId) || null,
    [builderNodes, selectedNodeId]
  );
  const latestRun = runs[0] || null;

  useEffect(() => {
    refresh();
  }, []);

  useEffect(() => {
    if (!agentId) {
      setRuns([]);
      return;
    }
    api.listAgentRuns(agentId).then(setRuns).catch((caught) => setError(toErrorMessage(caught)));
  }, [agentId]);

  useEffect(() => {
    if (!selectedAgent) {
      setEditName("");
      setEditDescription("");
      setEditCollections([]);
      setBuilderNodes(defaultNodes());
      setSelectedNodeId("retrieval");
      return;
    }

    const nodes = normalizeNodes(selectedAgent.definition.nodes);
    setEditName(selectedAgent.name);
    setEditDescription(selectedAgent.description || "");
    setEditCollections(selectedAgent.definition.collectionIds || []);
    setEditTopK(selectedAgent.definition.retrieval?.topK || 5);
    setEditVectorWeight(selectedAgent.definition.retrieval?.vectorWeight || 0.65);
    setEditThreshold(selectedAgent.definition.retrieval?.similarityThreshold || 0);
    setEditFallback(selectedAgent.definition.generation?.fallbackText || DEFAULT_FALLBACK);
    setBuilderNodes(nodes);
    setSelectedNodeId(nodes.find((node) => node.type !== "start" && node.type !== "end")?.id || nodes[0].id);
  }, [selectedAgent]);

  async function refresh() {
    setError("");
    try {
      const [agentResult, collectionResult] = await Promise.all([api.listAgents(), api.listCollections()]);
      setAgents(agentResult);
      setCollections(collectionResult);
      setSelectedCollections(collectionResult.map((collection) => collection.id));
      if (!agentId && agentResult.length > 0) {
        setAgentId(agentResult[0].id);
      }
    } catch (caught) {
      setError(toErrorMessage(caught));
    }
  }

  async function createAgent(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!name.trim()) return;
    setBusy(true);
    setError("");
    setMessage("");
    try {
      const created = await api.createAgent({
        name,
        description: description || null,
        definition: buildDefinition(selectedCollections, defaultBuilderOptions(), defaultNodes())
      });
      setName("");
      setDescription("");
      setMessage("Agent created.");
      await refresh();
      setAgentId(created.id);
    } catch (caught) {
      setError(toErrorMessage(caught));
    } finally {
      setBusy(false);
    }
  }

  async function saveSelectedAgent(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!agentId || !editName.trim()) return;
    setBusy(true);
    setError("");
    setMessage("");
    try {
      const updated = await api.updateAgent(agentId, {
        name: editName,
        description: editDescription || null,
        definition: buildDefinition(
          editCollections,
          {
            topK: editTopK,
            vectorWeight: editVectorWeight,
            similarityThreshold: editThreshold,
            fallbackText: editFallback
          },
          builderNodes
        )
      });
      setAgents((current) => current.map((agent) => (agent.id === updated.id ? updated : agent)));
      setMessage("Agent updated.");
    } catch (caught) {
      setError(toErrorMessage(caught));
    } finally {
      setBusy(false);
    }
  }

  async function runAgent(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!agentId || !runInput.trim()) return;
    setBusy(true);
    setError("");
    setMessage("");
    try {
      const run = await api.startAgentRun(agentId, runInput);
      setRuns((current) => [run, ...current]);
      setRunInput("");
      setMessage(`Run ${run.status.toLowerCase()}.`);
    } catch (caught) {
      setError(toErrorMessage(caught));
    } finally {
      setBusy(false);
    }
  }

  async function publishSelectedAgent() {
    if (!agentId) return;
    setBusy(true);
    setError("");
    try {
      const updated = await api.publishAgent(agentId);
      setAgents((current) => current.map((agent) => (agent.id === updated.id ? updated : agent)));
      setMessage("Agent published.");
    } catch (caught) {
      setError(toErrorMessage(caught));
    } finally {
      setBusy(false);
    }
  }

  async function deleteSelectedAgent() {
    if (!agentId || !selectedAgent) return;
    if (!window.confirm(`Delete agent "${selectedAgent.name}" and its runs?`)) return;
    setBusy(true);
    setError("");
    try {
      await api.deleteAgent(agentId);
      setMessage("Agent deleted.");
      setAgentId("");
      setRuns([]);
      await refresh();
    } catch (caught) {
      setError(toErrorMessage(caught));
    } finally {
      setBusy(false);
    }
  }

  function toggleCollection(collectionId: string) {
    setSelectedCollections((current) =>
      current.includes(collectionId) ? current.filter((id) => id !== collectionId) : [...current, collectionId]
    );
  }

  function toggleEditCollection(collectionId: string) {
    setEditCollections((current) =>
      current.includes(collectionId) ? current.filter((id) => id !== collectionId) : [...current, collectionId]
    );
  }

  function addNode() {
    const node = makeNode(newNodeType);
    setBuilderNodes((current) => {
      const nodes = normalizeNodes(current);
      const endIndex = nodes.findIndex((item) => item.type === "end");
      const insertAt = endIndex >= 0 ? endIndex : nodes.length;
      return [...nodes.slice(0, insertAt), node, ...nodes.slice(insertAt)];
    });
    setSelectedNodeId(node.id);
  }

  function removeSelectedNode() {
    if (!selectedNode || selectedNode.type === "start" || selectedNode.type === "end") return;
    setBuilderNodes((current) => normalizeNodes(current.filter((node) => node.id !== selectedNode.id)));
    setSelectedNodeId("retrieval");
  }

  function moveSelectedNode(direction: -1 | 1) {
    if (!selectedNode || selectedNode.type === "start" || selectedNode.type === "end") return;
    setBuilderNodes((current) => {
      const nodes = normalizeNodes(current);
      const index = nodes.findIndex((node) => node.id === selectedNode.id);
      const nextIndex = index + direction;
      if (nextIndex <= 0 || nextIndex >= nodes.length - 1) {
        return nodes;
      }
      const next = [...nodes];
      [next[index], next[nextIndex]] = [next[nextIndex], next[index]];
      return next;
    });
  }

  function updateSelectedNode(patch: Partial<AgentNode>) {
    if (!selectedNode) return;
    setBuilderNodes((current) =>
      current.map((node) => (node.id === selectedNode.id ? { ...node, ...patch } : node))
    );
  }

  function updateSelectedNodeConfig(patch: Record<string, unknown>) {
    if (!selectedNode) return;
    updateSelectedNode({
      config: {
        ...(selectedNode.config || {}),
        ...patch
      }
    });
  }

  return (
    <section className="page">
      <header className="page-header">
        <div>
          <p className="eyebrow">Agent Builder</p>
          <h2>{selectedAgent?.name || "Retrieval agent runtime"}</h2>
        </div>
        <div className="button-row">
          <button className="secondary-button" type="button" onClick={publishSelectedAgent} disabled={!agentId || busy}>
            Publish
          </button>
          <button className="danger-button" type="button" onClick={deleteSelectedAgent} disabled={!agentId || busy}>
            Delete
          </button>
        </div>
      </header>

      {error ? <p className="alert">{error}</p> : null}
      {message ? <p className="notice">{message}</p> : null}

      <div className="workspace-grid">
        <aside className="panel stack">
          <form className="stack compact-form" onSubmit={createAgent}>
            <h3>New agent</h3>
            <label>
              Name
              <input value={name} onChange={(event) => setName(event.target.value)} required />
            </label>
            <label>
              Description
              <textarea value={description} onChange={(event) => setDescription(event.target.value)} rows={3} />
            </label>
            <div className="list-box compact-list">
              {collections.map((collection) => (
                <label className="check-row" key={collection.id}>
                  <input
                    checked={selectedCollections.includes(collection.id)}
                    onChange={() => toggleCollection(collection.id)}
                    type="checkbox"
                  />
                  <span>
                    <strong>{collection.name}</strong>
                    <small>{collection.document_count} documents</small>
                  </span>
                </label>
              ))}
            </div>
            <button className="primary-button" type="submit" disabled={busy || !name.trim()}>
              Create
            </button>
          </form>

          <div className="stack">
            <h3>Agents</h3>
            <div className="list-box">
              {agents.map((agent) => (
                <button
                  className={agent.id === agentId ? "list-row selected" : "list-row"}
                  key={agent.id}
                  onClick={() => setAgentId(agent.id)}
                  type="button"
                >
                  <span>
                    <strong>{agent.name}</strong>
                    <small>{agent.published ? "Published" : "Draft"}</small>
                  </span>
                  <span className="count-badge">{agent.definition.collectionIds?.length || 0}</span>
                </button>
              ))}
              {agents.length === 0 ? <p className="empty-state">No agents yet.</p> : null}
            </div>
          </div>
        </aside>

        <main className="stack">
          <section className="panel stack">
            <div className="section-heading">
              <div>
                <h3>Canvas</h3>
                <p>Add, reorder, remove, and configure executable nodes.</p>
              </div>
              <span className={`status-pill ${selectedAgent?.published ? "ready" : ""}`}>
                {selectedAgent?.published ? "Published" : "Draft"}
              </span>
            </div>

            <div className="builder-canvas" aria-label="Agent graph canvas">
              {builderNodes.map((node, index) => (
                <div className="canvas-step" key={node.id}>
                  <button
                    className={node.id === selectedNodeId ? "canvas-node selected" : "canvas-node"}
                    disabled={!agentId}
                    onClick={() => setSelectedNodeId(node.id)}
                    type="button"
                  >
                    <strong>{node.label || node.id}</strong>
                    <span>{node.type}</span>
                  </button>
                  {index < builderNodes.length - 1 ? <span className="edge-arrow">-&gt;</span> : null}
                </div>
              ))}
            </div>

            <div className="builder-toolbar">
              <label>
                Add node
                <select value={newNodeType} onChange={(event) => setNewNodeType(event.target.value as AgentNodeType)}>
                  {ADDABLE_NODE_TYPES.map((type) => (
                    <option key={type.type} value={type.type}>
                      {type.label}
                    </option>
                  ))}
                </select>
              </label>
              <button className="secondary-button" type="button" onClick={addNode} disabled={!agentId}>
                Add
              </button>
              <button className="secondary-button" type="button" onClick={() => moveSelectedNode(-1)} disabled={!agentId}>
                Move left
              </button>
              <button className="secondary-button" type="button" onClick={() => moveSelectedNode(1)} disabled={!agentId}>
                Move right
              </button>
              <button
                className="danger-button"
                type="button"
                onClick={removeSelectedNode}
                disabled={!agentId || !selectedNode || selectedNode.type === "start" || selectedNode.type === "end"}
              >
                Remove
              </button>
            </div>
          </section>

          <section className="panel stack">
            <div className="section-heading">
              <div>
                <h3>Builder settings</h3>
                <p>Edit the selected agent and node configuration.</p>
              </div>
              <button className="secondary-button" type="button" onClick={refresh} disabled={busy}>
                Refresh
              </button>
            </div>
            <form className="stack" onSubmit={saveSelectedAgent}>
              <div className="control-grid">
                <label>
                  Agent name
                  <input value={editName} onChange={(event) => setEditName(event.target.value)} disabled={!agentId} />
                </label>
                <label>
                  Top K
                  <input
                    min={1}
                    max={50}
                    onChange={(event) => setEditTopK(Number(event.target.value))}
                    type="number"
                    value={editTopK}
                    disabled={!agentId}
                  />
                </label>
                <label>
                  Similarity threshold
                  <input
                    max={1}
                    min={-1}
                    onChange={(event) => setEditThreshold(Number(event.target.value))}
                    step={0.05}
                    type="number"
                    value={editThreshold}
                    disabled={!agentId}
                  />
                </label>
              </div>
              <label>
                Description
                <input
                  value={editDescription}
                  onChange={(event) => setEditDescription(event.target.value)}
                  disabled={!agentId}
                />
              </label>
              <label>
                Vector weight
                <input
                  max={1}
                  min={0}
                  onChange={(event) => setEditVectorWeight(Number(event.target.value))}
                  step={0.05}
                  type="range"
                  value={editVectorWeight}
                  disabled={!agentId}
                />
                <small>{editVectorWeight.toFixed(2)}</small>
              </label>
              <label>
                Fallback text
                <textarea
                  value={editFallback}
                  onChange={(event) => setEditFallback(event.target.value)}
                  rows={2}
                  disabled={!agentId}
                />
              </label>
              <div className="list-box compact-list">
                {collections.map((collection) => (
                  <label className="check-row" key={collection.id}>
                    <input
                      checked={editCollections.includes(collection.id)}
                      onChange={() => toggleEditCollection(collection.id)}
                      type="checkbox"
                      disabled={!agentId}
                    />
                    <span>
                      <strong>{collection.name}</strong>
                      <small>{collection.document_count} documents</small>
                    </span>
                  </label>
                ))}
              </div>

              <NodeInspector
                disabled={!agentId}
                editTopK={editTopK}
                editVectorWeight={editVectorWeight}
                editThreshold={editThreshold}
                node={selectedNode}
                onConfigChange={updateSelectedNodeConfig}
                onNodeChange={updateSelectedNode}
              />

              <button className="primary-button" type="submit" disabled={!agentId || !editName.trim() || busy}>
                Save builder
              </button>
            </form>
          </section>

          <section className="detail-grid">
            <article className="panel stack">
              <h3>Run agent</h3>
              <form className="stack" onSubmit={runAgent}>
                <label>
                  Input
                  <textarea
                    value={runInput}
                    onChange={(event) => setRunInput(event.target.value)}
                    rows={4}
                    placeholder="Ask the agent to retrieve and generate an answer"
                  />
                </label>
                <button className="primary-button" type="submit" disabled={!agentId || !runInput.trim() || busy}>
                  Start run
                </button>
              </form>
            </article>

            <article className="panel stack">
              <h3>Latest output</h3>
              {latestRun ? (
                <>
                  <span className={`status-pill ${latestRun.status === "COMPLETED" ? "ready" : ""}`}>
                    {latestRun.status}
                  </span>
                  <pre className="content-preview">{latestRun.output.answer || latestRun.output.error || "No output."}</pre>
                </>
              ) : (
                <p className="empty-state">No runs yet.</p>
              )}
            </article>
          </section>

          <section className="panel stack">
            <h3>Run events</h3>
            <div className="event-list">
              {(latestRun?.events || []).map((event, index) => (
                <div className="event-row" key={`${event.nodeId}-${event.event}-${index}`}>
                  <span className="count-badge">{event.nodeId}</span>
                  <strong>{event.event}</strong>
                  <small>{formatEventData(event.data)}</small>
                </div>
              ))}
              {!latestRun ? <p className="empty-state">No events yet.</p> : null}
            </div>
          </section>
        </main>
      </div>
    </section>
  );
}

function NodeInspector({
  disabled,
  editTopK,
  editVectorWeight,
  editThreshold,
  node,
  onConfigChange,
  onNodeChange
}: {
  disabled: boolean;
  editTopK: number;
  editVectorWeight: number;
  editThreshold: number;
  node: AgentNode | null;
  onConfigChange: (patch: Record<string, unknown>) => void;
  onNodeChange: (patch: Partial<AgentNode>) => void;
}) {
  if (!node) {
    return <p className="empty-state">Select a node to edit its settings.</p>;
  }

  const config = node.config || {};
  return (
    <div className="node-inspector">
      <div className="section-heading">
        <div>
          <h3>Selected node</h3>
          <p>{node.type}</p>
        </div>
        <span className="count-badge">{node.id}</span>
      </div>
      <label>
        Label
        <input
          value={node.label || ""}
          onChange={(event) => onNodeChange({ label: event.target.value })}
          disabled={disabled}
        />
      </label>

      {node.type === "retrieval" ? (
        <div className="control-grid">
          <label>
            Node top K
            <input
              min={1}
              max={50}
              onChange={(event) => onConfigChange({ topK: Number(event.target.value) })}
              type="number"
              value={Number(config.topK ?? editTopK)}
              disabled={disabled}
            />
          </label>
          <label>
            Node vector weight
            <input
              max={1}
              min={0}
              onChange={(event) => onConfigChange({ vectorWeight: Number(event.target.value) })}
              step={0.05}
              type="range"
              value={Number(config.vectorWeight ?? editVectorWeight)}
              disabled={disabled}
            />
            <small>{Number(config.vectorWeight ?? editVectorWeight).toFixed(2)}</small>
          </label>
          <label>
            Node threshold
            <input
              max={1}
              min={-1}
              onChange={(event) => onConfigChange({ similarityThreshold: Number(event.target.value) })}
              step={0.05}
              type="number"
              value={Number(config.similarityThreshold ?? editThreshold)}
              disabled={disabled}
            />
          </label>
        </div>
      ) : null}

      {node.type === "generate" ? (
        <label>
          Fallback override
          <textarea
            value={String(config.fallbackText || "")}
            onChange={(event) => onConfigChange({ fallbackText: event.target.value })}
            rows={2}
            disabled={disabled}
          />
        </label>
      ) : null}

      {node.type === "message" ? (
        <label>
          Message template
          <textarea
            value={String(config.template || "{answer}")}
            onChange={(event) => onConfigChange({ template: event.target.value })}
            rows={3}
            disabled={disabled}
          />
        </label>
      ) : null}

      {node.type === "code" ? (
        <div className="stack">
          <label>
            Python code (runs in Sandbox)
            <textarea
              value={String(config.code || "# Access retrieved context via the `context` variable\nprint(context)")}
              onChange={(event) => onConfigChange({ code: event.target.value })}
              rows={8}
              style={{ fontFamily: "monospace", fontSize: "0.83em" }}
              disabled={disabled}
            />
          </label>
          <label>
            Timeout (seconds)
            <input
              type="number"
              min={1}
              max={30}
              value={Number(config.timeout_seconds ?? 10)}
              onChange={(event) => onConfigChange({ timeout_seconds: Number(event.target.value) })}
              disabled={disabled}
            />
          </label>
          <p style={{ fontSize: "0.8em", color: "var(--muted)" }}>
            Code node runs after retrieval. Output is captured as stdout and shown in run events.
            Writes to files become artifacts in the run output.
          </p>
        </div>
      ) : null}
    </div>
  );
}

function buildDefinition(
  collectionIds: string[],
  options: {
    topK: number;
    vectorWeight: number;
    similarityThreshold: number;
    fallbackText: string;
  },
  nodes: AgentNode[]
): Agent["definition"] {
  const normalizedNodes = normalizeNodes(nodes);
  return {
    version: 1,
    nodes: normalizedNodes,
    edges: makeLinearEdges(normalizedNodes),
    collectionIds,
    retrieval: {
      topK: options.topK,
      vectorWeight: options.vectorWeight,
      similarityThreshold: options.similarityThreshold
    },
    generation: {
      mode: "local-grounded",
      fallbackText: options.fallbackText
    }
  };
}

function defaultBuilderOptions() {
  return {
    topK: 5,
    vectorWeight: 0.65,
    similarityThreshold: 0,
    fallbackText: DEFAULT_FALLBACK
  };
}

function defaultNodes(): AgentNode[] {
  return [
    { id: "start", type: "start", label: "Start" },
    { id: "retrieval", type: "retrieval", label: "Retrieve" },
    { id: "generate", type: "generate", label: "Generate" },
    { id: "message", type: "message", label: "Message", config: { template: "{answer}" } },
    { id: "end", type: "end", label: "End" }
  ];
}

function makeNode(type: AgentNodeType): AgentNode {
  const id = `${type}_${Date.now().toString(36)}`;
  if (type === "message") {
    return { id, type, label: "Message", config: { template: "{answer}" } };
  }
  if (type === "retrieval") {
    return { id, type, label: "Retrieve" };
  }
  if (type === "generate") {
    return { id, type, label: "Generate" };
  }
  if (type === "code") {
    return {
      id, type, label: "Code",
      config: {
        code: "# Retrieved context is available as a variable\nprint('Running in Sandbox')\nprint(context)\n",
        timeout_seconds: 10
      }
    };
  }
  return { id, type, label: type };
}

function normalizeNodes(nodes: AgentNode[] | undefined): AgentNode[] {
  const source = nodes && nodes.length > 0 ? nodes : defaultNodes();
  const middle = source.filter((node) => node.type !== "start" && node.type !== "end");
  return [
    source.find((node) => node.type === "start") || { id: "start", type: "start", label: "Start" },
    ...middle.map((node) => ({
      ...node,
      id: node.id || `${node.type}_${Date.now().toString(36)}`,
      label: node.label || node.type
    })),
    source.find((node) => node.type === "end") || { id: "end", type: "end", label: "End" }
  ];
}

function makeLinearEdges(nodes: AgentNode[]) {
  return nodes.slice(0, -1).map((node, index) => ({
    from: node.id,
    to: nodes[index + 1].id
  }));
}

function formatEventData(data: Record<string, unknown>) {
  const text = JSON.stringify(data);
  return text.length > 120 ? `${text.slice(0, 117)}...` : text;
}

function toErrorMessage(error: unknown) {
  return error instanceof ApiError ? error.message : "Request failed.";
}
