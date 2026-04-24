export function AdminPage() {
  return (
    <section className="page">
      <header className="page-header">
        <div>
          <p className="eyebrow">Admin Dashboard</p>
          <h2>Operations and governance</h2>
        </div>
      </header>
      <div className="grid cards-3">
        <article className="panel">
          <h3>Tenants</h3>
          <p>Tenant isolation, quotas, and registration policy controls will live here.</p>
        </article>
        <article className="panel">
          <h3>Providers</h3>
          <p>LLM, embedding, reranker, ASR, and TTS provider registration panels.</p>
        </article>
        <article className="panel">
          <h3>Health</h3>
          <p>Queue depth, service health, and metrics export aligned with the architecture.</p>
        </article>
      </div>
    </section>
  );
}

