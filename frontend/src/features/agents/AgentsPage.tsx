export function AgentsPage() {
  return (
    <section className="page">
      <header className="page-header">
        <div>
          <p className="eyebrow">Agent Builder</p>
          <h2>Workflow canvas placeholder</h2>
        </div>
        <button className="primary-button" type="button">
          Create agent
        </button>
      </header>
      <div className="grid cards-2">
        <article className="panel">
          <h3>Execution model</h3>
          <p>
            Planned node types include Start, Retrieval, Generate, Code, Branch, Loop,
            Tool Invocation, Chart, Message, and End.
          </p>
        </article>
        <article className="panel">
          <h3>Versioning and publishing</h3>
          <p>
            Published agent versions will expose a public URL, embed widget, webhook, and
            OpenAI-compatible endpoint.
          </p>
        </article>
      </div>
    </section>
  );
}

