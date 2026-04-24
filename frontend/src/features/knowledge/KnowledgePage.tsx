const roadmap = [
  "Collection list and detail",
  "Document upload and parse progress",
  "Chunk review and retrieval testing"
];

export function KnowledgePage() {
  return (
    <section className="page">
      <header className="page-header">
        <div>
          <p className="eyebrow">Knowledge Workspace</p>
          <h2>Collections and documents</h2>
        </div>
        <button className="primary-button" type="button">
          New collection
        </button>
      </header>
      <div className="grid cards-2">
        <article className="panel">
          <h3>Current starter scope</h3>
          <p>
            The backend already exposes collection and document endpoints. This screen is
            ready to be connected to the live API next.
          </p>
        </article>
        <article className="panel">
          <h3>Planned modules</h3>
          <ul className="simple-list">
            {roadmap.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        </article>
      </div>
    </section>
  );
}

