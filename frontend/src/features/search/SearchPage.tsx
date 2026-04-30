import { FormEvent, useEffect, useState } from "react";

import { Collection, Document, RetrievalHit, api } from "../../api/client";

export function SearchPage() {
  const [collections, setCollections] = useState<Collection[]>([]);
  const [documents, setDocuments] = useState<Document[]>([]);
  const [selectedCollections, setSelectedCollections] = useState<string[]>([]);
  const [selectedDocuments, setSelectedDocuments] = useState<string[]>([]);
  const [query, setQuery] = useState("");
  const [topK, setTopK] = useState(8);
  const [vectorWeight, setVectorWeight] = useState(0.6);
  const [rerank, setRerank] = useState(true);
  const [hits, setHits] = useState<RetrievalHit[]>([]);
  const [embeddingModel, setEmbeddingModel] = useState("nomic-embed-text");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    api
      .listCollections()
      .then((result) => {
        setCollections(result);
        setSelectedCollections(result.map((collection) => collection.id));
      })
      .catch((caught) => setError(toMessage(caught)));
  }, []);

  useEffect(() => {
    let cancelled = false;
    async function loadDocuments() {
      const results = await Promise.allSettled(selectedCollections.map((id) => api.listDocuments(id)));
      if (cancelled) return;
      const nextDocuments = results.flatMap((result) => (result.status === "fulfilled" ? result.value : []));
      setDocuments(nextDocuments);
      setSelectedDocuments((current) => current.filter((id) => nextDocuments.some((document) => document.id === id)));
    }
    loadDocuments().catch((caught) => setError(toMessage(caught)));
    return () => {
      cancelled = true;
    };
  }, [selectedCollections]);

  async function search(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!query.trim()) return;
    setBusy(true);
    setError("");
    try {
      const result = await api.retrieve({
        query,
        top_k: topK,
        vector_weight: vectorWeight,
        collection_ids: selectedCollections,
        document_ids: selectedDocuments,
        embedding_model: embeddingModel,
        rerank
      });
      setHits(result.hits);
      setEmbeddingModel(result.embedding_model);
      setVectorWeight(result.vector_weight);
    } catch (caught) {
      setError(toMessage(caught));
    } finally {
      setBusy(false);
    }
  }

  function toggleCollection(collectionId: string) {
    setSelectedCollections((current) =>
      current.includes(collectionId) ? current.filter((id) => id !== collectionId) : [...current, collectionId]
    );
  }

  function toggleDocument(documentId: string) {
    setSelectedDocuments((current) =>
      current.includes(documentId) ? current.filter((id) => id !== documentId) : [...current, documentId]
    );
  }

  return (
    <section className="page">
      <header className="page-header">
        <div>
          <p className="eyebrow">AI Search</p>
          <h2>Hybrid retrieval</h2>
        </div>
      </header>

      {error ? <p className="alert">{error}</p> : null}

      <section className="panel stack">
        <form className="stack" onSubmit={search}>
          <label>
            Query
            <input value={query} onChange={(event) => setQuery(event.target.value)} />
          </label>
          <div className="control-grid">
            <label>
              Top K
              <input min={1} max={50} type="range" value={topK} onChange={(event) => setTopK(Number(event.target.value))} />
              <small>{topK}</small>
            </label>
            <label>
              Vector weight
              <input
                min={0}
                max={1}
                step={0.05}
                type="range"
                value={vectorWeight}
                onChange={(event) => setVectorWeight(Number(event.target.value))}
              />
              <small>{vectorWeight.toFixed(2)}</small>
            </label>
            <label>
              Embedding model
              <input value={embeddingModel} onChange={(event) => setEmbeddingModel(event.target.value)} />
            </label>
          </div>

          <label className="inline-check">
            <input checked={rerank} onChange={(event) => setRerank(event.target.checked)} type="checkbox" />
            Rerank results
          </label>

          <div className="collection-filter">
            {collections.map((collection) => (
              <label className="check-row" key={collection.id}>
                <input checked={selectedCollections.includes(collection.id)} onChange={() => toggleCollection(collection.id)} type="checkbox" />
                <span>{collection.name}</span>
              </label>
            ))}
          </div>

          <div className="collection-filter">
            {documents.map((document) => (
              <label className="check-row" key={document.id}>
                <input checked={selectedDocuments.includes(document.id)} onChange={() => toggleDocument(document.id)} type="checkbox" />
                <span>
                  <strong>{document.name}</strong>
                  <small>{document.status}</small>
                </span>
              </label>
            ))}
          </div>

          <button className="primary-button" type="submit" disabled={busy || !query.trim()}>
            Search
          </button>
        </form>
      </section>

      <section className="stack">
        {hits.map((hit) => {
          const graphContext = Array.isArray(hit.metadata.graph_context) ? hit.metadata.graph_context : [];
          return (
            <article className="panel result-card" key={hit.chunk_id}>
              <div className="section-heading">
                <div>
                  <strong>{hit.metadata.document_name ? String(hit.metadata.document_name) : hit.document_id}</strong>
                  {graphContext.length > 0 ? <span className="count-badge">graph context</span> : null}
                </div>
                <span className="score-badge">{hit.score.toFixed(3)}</span>
              </div>
              <p>{hit.snippet || hit.text}</p>
              <div className="score-grid">
                <small>First stage: {formatScore(hit.metadata.first_stage_score)}</small>
                <small>Rerank: {formatScore(hit.metadata.rerank_score)}</small>
              </div>
              {graphContext.length > 0 ? (
                <div className="graph-context">
                  {graphContext.map((line) => (
                    <small key={line}>{line}</small>
                  ))}
                </div>
              ) : null}
            </article>
          );
        })}
        {hits.length === 0 ? <p className="empty-state">No results yet.</p> : null}
      </section>
    </section>
  );
}

function formatScore(value: unknown) {
  return typeof value === "number" ? value.toFixed(3) : "-";
}

function toMessage(error: unknown) {
  return error instanceof Error ? error.message : "Request failed.";
}
