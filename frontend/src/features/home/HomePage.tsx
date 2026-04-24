export function HomePage() {
  return (
    <section className="page">
      <div className="hero-card">
        <p className="eyebrow">Platform Overview</p>
        <h2>Build a production-grade RAG and agent platform from one foundation.</h2>
        <p>
          This starter maps directly to the spec: knowledge collections, grounded chat,
          agent workflows, provider management, and multi-tenant operations.
        </p>
      </div>
      <div className="grid cards-3">
        <article className="panel">
          <h3>Knowledge</h3>
          <p>Collections, documents, ingestion pipelines, chunking, and retrieval tuning.</p>
        </article>
        <article className="panel">
          <h3>Chat</h3>
          <p>Cited answers, streaming responses, retrieval controls, and model comparison.</p>
        </article>
        <article className="panel">
          <h3>Agents</h3>
          <p>Visual workflows with retrieval, code execution, tools, and webhook publishing.</p>
        </article>
      </div>
    </section>
  );
}

