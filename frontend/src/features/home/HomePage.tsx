import { useEffect, useState } from "react";
import { Link } from "react-router-dom";

import { Agent, Collection, Conversation, api } from "../../api/client";

export function HomePage() {
  const [health, setHealth] = useState("checking");
  const [collections, setCollections] = useState<Collection[]>([]);
  const [agents, setAgents] = useState<Agent[]>([]);
  const [conversations, setConversations] = useState<Conversation[]>([]);

  useEffect(() => {
    api.health().then((result) => setHealth(result.status)).catch(() => setHealth("offline"));
    api.listCollections().then(setCollections).catch(() => setCollections([]));
    api.listAgents().then(setAgents).catch(() => setAgents([]));
    api.listConversations().then(setConversations).catch(() => setConversations([]));
  }, []);

  const ready = health === "healthy" || health === "ok";

  return (
    <section className="page">
      <header className="page-header">
        <div>
          <p className="eyebrow">Platform Overview</p>
          <h2>Workspace status</h2>
        </div>
        <span className={`status-pill ${ready ? "ready" : ""}`}>{health}</span>
      </header>

      <div className="summary-grid">
        <article className="metric-card">
          <span>Collections</span>
          <strong>{collections.length}</strong>
        </article>
        <article className="metric-card">
          <span>Documents</span>
          <strong>{collections.reduce((total, collection) => total + collection.document_count, 0)}</strong>
        </article>
        <article className="metric-card">
          <span>Agents</span>
          <strong>{agents.length}</strong>
        </article>
        <article className="metric-card">
          <span>Conversations</span>
          <strong>{conversations.length}</strong>
        </article>
      </div>

      <div className="workbench-grid">
        <Link className="panel action-panel" to="/knowledge">
          <p className="eyebrow">Knowledge</p>
          <h3>Manage collections and uploads</h3>
          <p>Inspect parsing, chunks, graph triples, and collection retrieval defaults.</p>
        </Link>
        <Link className="panel action-panel" to="/search">
          <p className="eyebrow">Retrieval</p>
          <h3>Test ranked passage search</h3>
          <p>Tune top K and vector weight against live chunks and graph context.</p>
        </Link>
        <Link className="panel action-panel" to="/chat">
          <p className="eyebrow">Chat</p>
          <h3>Ask a grounded assistant</h3>
          <p>Stream cited answers from the current collections and conversations API.</p>
        </Link>
        <Link className="panel action-panel" to="/agents">
          <p className="eyebrow">Agents</p>
          <h3>Build retrieval workflows</h3>
          <p>Create, publish, and run local-first agent graphs backed by the same knowledge base.</p>
        </Link>
      </div>

      <article className="panel">
        <p className="eyebrow">Implementation Layer</p>
        <h3>Current product surface</h3>
        <p>
          This merged app now uses the M6 backend for ingestion, re-indexing, graph extraction,
          retrieval, cited chat, admin operations, and the restored agent builder.
        </p>
      </article>
    </section>
  );
}
