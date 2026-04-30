import { FormEvent, useEffect, useMemo, useState } from "react";

import { Chunk, Collection, Connector, Document, DocumentStatus, GraphTriple, api } from "../../api/client";

const chunkTemplates = ["general", "qa", "small-to-big", "sentence-window"];

export function KnowledgePage() {
  const [collections, setCollections] = useState<Collection[]>([]);
  const [documents, setDocuments] = useState<Document[]>([]);
  const [chunks, setChunks] = useState<Chunk[]>([]);
  const [triples, setTriples] = useState<GraphTriple[]>([]);
  const [statuses, setStatuses] = useState<Record<string, DocumentStatus>>({});
  const [selectedCollectionId, setSelectedCollectionId] = useState("");
  const [selectedDocumentId, setSelectedDocumentId] = useState("");
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [uploadFiles, setUploadFiles] = useState<File[]>([]);
  const [tagFilter, setTagFilter] = useState("");
  const [tagDraft, setTagDraft] = useState<Record<string, string>>({});
  const [entityFilter, setEntityFilter] = useState("");
  const [dragActive, setDragActive] = useState(false);
  const [connectors, setConnectors] = useState<Connector[]>([]);
  const [newConnectorKind, setNewConnectorKind] = useState<Connector["kind"]>("web_crawler");
  const [newConnectorName, setNewConnectorName] = useState("");
  const [newConnectorConfig, setNewConnectorConfig] = useState('{"urls": ["https://example.com/docs/"], "depth": 1, "max_pages": 30}');
  const [showConnectorForm, setShowConnectorForm] = useState(false);

  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  const selectedCollection = useMemo(
    () => collections.find((collection) => collection.id === selectedCollectionId) || null,
    [collections, selectedCollectionId]
  );
  const selectedDocument = useMemo(
    () => documents.find((document) => document.id === selectedDocumentId) || null,
    [documents, selectedDocumentId]
  );

  useEffect(() => {
    refreshCollections();
  }, []);

  useEffect(() => {
    if (!selectedCollectionId) {
      setDocuments([]);
      setTriples([]);
      setConnectors([]);
      return;
    }
    refreshDocuments(selectedCollectionId, tagFilter);
    refreshCollectionGraph(selectedCollectionId, entityFilter);
    refreshConnectors(selectedCollectionId);
  }, [selectedCollectionId, tagFilter]);

  useEffect(() => {
    if (!selectedDocumentId) {
      setChunks([]);
      return;
    }
    refreshDocumentDetail(selectedDocumentId);
  }, [selectedDocumentId]);

  useEffect(() => {
    const activeDocuments = documents.filter((document) => !isTerminalStatus(document.status));
    if (activeDocuments.length === 0) return;
    const timer = window.setInterval(async () => {
      const statusPairs = await Promise.all(
        activeDocuments.map(async (document) => [document.id, await api.getDocumentStatus(document.id)] as const)
      );
      setStatuses((current) => ({ ...current, ...Object.fromEntries(statusPairs) }));
      if (selectedCollectionId) {
        await refreshDocuments(selectedCollectionId, tagFilter);
      }
    }, 2000);
    return () => window.clearInterval(timer);
  }, [documents, selectedCollectionId, tagFilter]);

  const availableTags = useMemo(
    () => Array.from(new Set(documents.flatMap((document) => document.tags || []))).sort(),
    [documents]
  );

  async function refreshCollections() {
    setError("");
    try {
      const result = await api.listCollections();
      setCollections(result);
      if (!selectedCollectionId && result.length > 0) {
        setSelectedCollectionId(result[0].id);
      }
    } catch (caught) {
      setError(toMessage(caught));
    }
  }

  async function refreshDocuments(collectionId: string, tag = "") {
    try {
      const result = tag ? await api.listDocumentsByTag(collectionId, tag) : await api.listDocuments(collectionId);
      setDocuments(result);
      setTagDraft(Object.fromEntries(result.map((document) => [document.id, (document.tags || []).join(", ")])));
      setSelectedDocumentId((current) =>
        result.some((document) => document.id === current) ? current : result[0]?.id || ""
      );
      const statusPairs = await Promise.all(
        result.map(async (document) => [document.id, await api.getDocumentStatus(document.id)] as const)
      );
      setStatuses(Object.fromEntries(statusPairs));
    } catch (caught) {
      setError(toMessage(caught));
    }
  }

  async function refreshDocumentDetail(documentId: string) {
    try {
      const [chunkResult, graphResult] = await Promise.all([
        api.listChunks(documentId).catch(() => []),
        api.listDocumentGraph(documentId).catch(() => [])
      ]);
      setChunks(chunkResult);
      setTriples(graphResult);
    } catch (caught) {
      setError(toMessage(caught));
    }
  }

  async function refreshCollectionGraph(collectionId: string, entity = "") {
    try {
      setTriples(await api.listCollectionGraph(collectionId, { entity }));
    } catch (caught) {
      setError(toMessage(caught));
    }
  }

  async function refreshConnectors(collectionId: string) {
    try {
      setConnectors(await api.listConnectors(collectionId));
    } catch {
      // Non-fatal — connectors are a secondary feature
    }
  }

  async function createConnector(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selectedCollectionId || !newConnectorName.trim()) return;
    setBusy(true);
    setError("");
    try {
      let config: Record<string, unknown> = {};
      try { config = JSON.parse(newConnectorConfig); } catch { throw new Error("Connector config is not valid JSON."); }
      await api.createConnector({
        collection_id: selectedCollectionId,
        name: newConnectorName.trim(),
        kind: newConnectorKind,
        config,
      });
      setNewConnectorName("");
      setShowConnectorForm(false);
      setNotice("Connector created.");
      await refreshConnectors(selectedCollectionId);
    } catch (caught) {
      setError(toMessage(caught));
    } finally {
      setBusy(false);
    }
  }

  async function syncConnector(connectorId: string) {
    setBusy(true);
    setError("");
    try {
      const report = await api.syncConnector(connectorId);
      setNotice(`Sync complete: ${report.ingested} ingested, ${report.skipped_duplicate} skipped.`);
      if (selectedCollectionId) {
        await refreshConnectors(selectedCollectionId);
        await refreshDocuments(selectedCollectionId, tagFilter);
      }
    } catch (caught) {
      setError(toMessage(caught));
    } finally {
      setBusy(false);
    }
  }

  async function deleteConnector(connectorId: string, name: string) {
    if (!window.confirm(`Delete connector "${name}"?`)) return;
    setBusy(true);
    setError("");
    try {
      await api.deleteConnector(connectorId);
      setNotice("Connector deleted.");
      if (selectedCollectionId) await refreshConnectors(selectedCollectionId);
    } catch (caught) {
      setError(toMessage(caught));
    } finally {
      setBusy(false);
    }
  }

  function connectorConfigTemplate(kind: Connector["kind"]): string {
    if (kind === "web_crawler") return '{"urls": ["https://example.com/docs/"], "depth": 1, "max_pages": 30}';
    if (kind === "s3") return '{"bucket": "my-bucket", "prefix": "docs/", "region": "us-east-1"}';
    return '{"path": "/data/documents"}';
  }

  async function createCollection(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!name.trim()) return;
    setBusy(true);
    setError("");
    setNotice("");
    try {
      const created = await api.createCollection({
        name,
        description: description || null,
        embedding_model: "nomic-embed-text",
        chunk_template: "small-to-big",
        top_k: 8,
        vector_weight: 0.6
      });
      setName("");
      setDescription("");
      setNotice("Collection created.");
      await refreshCollections();
      setSelectedCollectionId(created.id);
    } catch (caught) {
      setError(toMessage(caught));
    } finally {
      setBusy(false);
    }
  }

  async function saveCollection(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selectedCollection) return;
    const form = new FormData(event.currentTarget);
    setBusy(true);
    setError("");
    try {
      const updated = await api.updateCollection(selectedCollection.id, {
        name: String(form.get("name") || selectedCollection.name),
        description: String(form.get("description") || ""),
        embedding_model: String(form.get("embedding_model") || selectedCollection.embedding_model),
        chunk_template: String(form.get("chunk_template") || selectedCollection.chunk_template),
        system_prompt: String(form.get("system_prompt") || ""),
        top_k: Number(form.get("top_k") || selectedCollection.top_k),
        vector_weight: Number(form.get("vector_weight") || selectedCollection.vector_weight)
      });
      setCollections((current) => current.map((collection) => (collection.id === updated.id ? updated : collection)));
      setNotice("Collection settings saved.");
    } catch (caught) {
      setError(toMessage(caught));
    } finally {
      setBusy(false);
    }
  }

  async function upload(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selectedCollectionId || uploadFiles.length === 0) return;
    setBusy(true);
    setError("");
    setNotice("");
    try {
      if (uploadFiles.length === 1) {
        await api.uploadDocument(selectedCollectionId, uploadFiles[0]);
      } else {
        await api.bulkUploadDocuments(selectedCollectionId, uploadFiles.slice(0, 20));
      }
      setUploadFiles([]);
      setNotice("Upload accepted. Inline workers will parse and index in development mode.");
      await refreshDocuments(selectedCollectionId, tagFilter);
    } catch (caught) {
      setError(toMessage(caught));
    } finally {
      setBusy(false);
    }
  }

  async function reindex(document: Document) {
    if (!selectedCollection) return;
    setBusy(true);
    setError("");
    try {
      await api.reindexDocument(document.id, {
        chunk_template: selectedCollection.chunk_template,
        embedding_model: selectedCollection.embedding_model
      });
      setNotice("Re-index started.");
      await refreshDocuments(selectedCollection.id, tagFilter);
    } catch (caught) {
      setError(toMessage(caught));
    } finally {
      setBusy(false);
    }
  }

  async function removeCollection() {
    if (!selectedCollection || !window.confirm(`Delete "${selectedCollection.name}" and all documents?`)) return;
    setBusy(true);
    setError("");
    try {
      await api.deleteCollection(selectedCollection.id);
      setSelectedCollectionId("");
      setSelectedDocumentId("");
      await refreshCollections();
      setNotice("Collection deleted.");
    } catch (caught) {
      setError(toMessage(caught));
    } finally {
      setBusy(false);
    }
  }

  async function removeDocument(document: Document) {
    if (!window.confirm(`Delete "${document.name}"?`)) return;
    setBusy(true);
    setError("");
    try {
      await api.deleteDocument(document.id);
      await refreshDocuments(document.collection_id, tagFilter);
      setNotice("Document deleted.");
    } catch (caught) {
      setError(toMessage(caught));
    } finally {
      setBusy(false);
    }
  }

  async function saveTags(document: Document) {
    setBusy(true);
    setError("");
    try {
      const tags = (tagDraft[document.id] || "")
        .split(",")
        .map((tag) => tag.trim())
        .filter(Boolean)
        .slice(0, 20);
      const updated = await api.setDocumentTags(document.id, tags);
      setDocuments((current) => current.map((item) => (item.id === updated.id ? updated : item)));
      setTagDraft((current) => ({ ...current, [updated.id]: updated.tags.join(", ") }));
      setNotice("Document tags saved.");
    } catch (caught) {
      setError(toMessage(caught));
    } finally {
      setBusy(false);
    }
  }

  async function handleFiles(files: File[]) {
    if (!selectedCollectionId || files.length === 0) return;
    setUploadFiles(files.slice(0, 20));
  }

  return (
    <section className="page">
      <header className="page-header">
        <div>
          <p className="eyebrow">Knowledge Workspace</p>
          <h2>Collections and documents</h2>
        </div>
        <button className="secondary-button" type="button" onClick={refreshCollections}>
          Refresh
        </button>
      </header>

      {error ? <p className="alert">{error}</p> : null}
      {notice ? <p className="notice">{notice}</p> : null}

      <div className="workspace-grid">
        <aside className="panel stack">
          <form className="stack" onSubmit={createCollection}>
            <h3>New collection</h3>
            <label>
              Name
              <input value={name} onChange={(event) => setName(event.target.value)} required />
            </label>
            <label>
              Description
              <textarea value={description} onChange={(event) => setDescription(event.target.value)} rows={3} />
            </label>
            <button className="primary-button" type="submit" disabled={busy || !name.trim()}>
              Create
            </button>
          </form>

          <div className="stack">
            <h3>Collections</h3>
            {collections.map((collection) => (
              <button
                className={collection.id === selectedCollectionId ? "list-row selected" : "list-row"}
                key={collection.id}
                onClick={() => {
                  setSelectedCollectionId(collection.id);
                  setSelectedDocumentId("");
                }}
                type="button"
              >
                <span>
                  <strong>{collection.name}</strong>
                  <small>{collection.chunk_template}</small>
                </span>
                <span className="count-badge">{collection.document_count}</span>
              </button>
            ))}
          </div>
        </aside>

        <main className="stack">
          {selectedCollection ? (
            <section className="panel stack">
              <div className="section-heading">
                <div>
                  <h3>{selectedCollection.name}</h3>
                  <p>{selectedCollection.description || "No description"}</p>
                </div>
                <button className="danger-button" type="button" onClick={removeCollection} disabled={busy}>
                  Delete collection
                </button>
              </div>
              <form className="stack" key={selectedCollection.id} onSubmit={saveCollection}>
                <div className="control-grid">
                  <label>
                    Name
                    <input name="name" defaultValue={selectedCollection.name} />
                  </label>
                  <label>
                    Embedding model
                    <input name="embedding_model" defaultValue={selectedCollection.embedding_model} />
                  </label>
                  <label>
                    Chunk template
                    <select name="chunk_template" defaultValue={selectedCollection.chunk_template}>
                      {chunkTemplates.map((template) => (
                        <option key={template} value={template}>
                          {template}
                        </option>
                      ))}
                    </select>
                  </label>
                  <label>
                    Top K
                    <input min={1} max={50} name="top_k" type="number" defaultValue={selectedCollection.top_k} />
                  </label>
                  <label>
                    Vector weight
                    <input
                      min={0}
                      max={1}
                      step={0.05}
                      name="vector_weight"
                      type="number"
                      defaultValue={selectedCollection.vector_weight}
                    />
                  </label>
                </div>
                <label>
                  Description
                  <input name="description" defaultValue={selectedCollection.description || ""} />
                </label>
                <label>
                  Collection system prompt
                  <textarea name="system_prompt" rows={3} defaultValue={selectedCollection.system_prompt || ""} />
                </label>
                <button className="primary-button" type="submit" disabled={busy}>
                  Save settings
                </button>
              </form>
            </section>
          ) : null}

          {selectedCollection ? (
            <section className="panel stack">
              <div className="section-heading">
                <div>
                  <h3>Connectors</h3>
                  <p>Automatically sync documents from external sources into this collection.</p>
                </div>
                <button className="secondary-button" type="button" onClick={() => setShowConnectorForm((v) => !v)}>
                  {showConnectorForm ? "Cancel" : "+ Add connector"}
                </button>
              </div>

              {showConnectorForm ? (
                <form className="stack" onSubmit={createConnector}>
                  <div className="control-grid">
                    <label>
                      Name
                      <input
                        value={newConnectorName}
                        onChange={(e) => setNewConnectorName(e.target.value)}
                        required
                        placeholder="My web crawler"
                      />
                    </label>
                    <label>
                      Kind
                      <select
                        value={newConnectorKind}
                        onChange={(e) => {
                          const k = e.target.value as Connector["kind"];
                          setNewConnectorKind(k);
                          setNewConnectorConfig(connectorConfigTemplate(k));
                        }}
                      >
                        <option value="web_crawler">Web Crawler</option>
                        <option value="local_folder">Local Folder</option>
                        <option value="s3">S3 Bucket</option>
                      </select>
                    </label>
                  </div>
                  <label>
                    Config (JSON)
                    <textarea
                      value={newConnectorConfig}
                      onChange={(e) => setNewConnectorConfig(e.target.value)}
                      rows={4}
                      style={{ fontFamily: "monospace", fontSize: "0.85em" }}
                    />
                  </label>
                  <button className="primary-button" type="submit" disabled={busy || !newConnectorName.trim()}>
                    Create connector
                  </button>
                </form>
              ) : null}

              {connectors.length === 0 && !showConnectorForm ? (
                <p className="empty-state">No connectors. Add one to auto-sync documents from URLs, folders, or S3.</p>
              ) : (
                connectors.map((c) => (
                  <div key={c.id} className="list-row">
                    <span>
                      <strong>{c.name}</strong>
                      <small>{c.kind} &middot; every {Math.round(c.sync_interval_seconds / 60)}m</small>
                      {c.last_error ? <small style={{ color: "var(--danger, #e74c3c)" }}>{c.last_error}</small> : null}
                    </span>
                    <span className="button-row">
                      <span className={`status-pill ${c.enabled ? "ready" : ""}`}>
                        {c.enabled ? "enabled" : "paused"}
                      </span>
                      <small>synced {c.last_synced_count}</small>
                      <button
                        className="secondary-button small-button"
                        type="button"
                        onClick={() => syncConnector(c.id)}
                        disabled={busy}
                      >
                        Sync now
                      </button>
                      <button
                        className="danger-button small-button"
                        type="button"
                        onClick={() => deleteConnector(c.id, c.name)}
                        disabled={busy}
                      >
                        Delete
                      </button>
                    </span>
                  </div>
                ))
              )}
            </section>
          ) : null}

          <section className="panel stack">
            <div className="section-heading">
              <h3>Documents</h3>
              <div className="button-row">
                <select value={tagFilter} onChange={(event) => setTagFilter(event.target.value)} disabled={!selectedCollectionId}>
                  <option value="">All tags</option>
                  {availableTags.map((tag) => (
                    <option key={tag} value={tag}>
                      {tag}
                    </option>
                  ))}
                </select>
              </div>
            </div>
            <form
              className={`upload-zone ${dragActive ? "active" : ""}`}
              onDragEnter={(event) => {
                event.preventDefault();
                setDragActive(true);
              }}
              onDragOver={(event) => event.preventDefault()}
              onDragLeave={() => setDragActive(false)}
              onDrop={(event) => {
                event.preventDefault();
                setDragActive(false);
                handleFiles(Array.from(event.dataTransfer.files));
              }}
              onSubmit={upload}
            >
              <input
                multiple
                onChange={(event) => handleFiles(Array.from(event.target.files || []))}
                type="file"
              />
              <button className="primary-button" type="submit" disabled={!selectedCollectionId || busy || uploadFiles.length === 0}>
                Upload {uploadFiles.length > 1 ? `${uploadFiles.length} files` : ""}
              </button>
            </form>
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>Name</th>
                    <th>Tags</th>
                    <th>Status</th>
                    <th>Parser</th>
                    <th>Progress</th>
                    <th>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {documents.map((document) => (
                    <tr
                      className={document.id === selectedDocumentId ? "selected-row" : ""}
                      key={document.id}
                      onClick={() => setSelectedDocumentId(document.id)}
                    >
                      <td>{document.name}</td>
                      <td>
                        <div className="tag-editor">
                          <input
                            aria-label={`Tags for ${document.name}`}
                            onChange={(event) =>
                              setTagDraft((current) => ({ ...current, [document.id]: event.target.value }))
                            }
                            onClick={(event) => event.stopPropagation()}
                            value={tagDraft[document.id] || ""}
                            placeholder="tag-a, tag-b"
                          />
                          <button
                            className="secondary-button small-button"
                            disabled={busy}
                            onClick={(event) => {
                              event.stopPropagation();
                              saveTags(document);
                            }}
                            type="button"
                          >
                            Save
                          </button>
                        </div>
                      </td>
                      <td>
                        <span className={`status-pill ${document.status === "READY" ? "ready" : ""}`}>
                          {document.status}
                        </span>
                      </td>
                      <td>{document.parser_name || "-"}</td>
                      <td>{statuses[document.id]?.progress_pct ?? 0}%</td>
                      <td>
                        <div className="button-row">
                          <button
                            type="button"
                            className="secondary-button small-button"
                            onClick={(event) => {
                              event.stopPropagation();
                              reindex(document);
                            }}
                          >
                            Re-index
                          </button>
                          <button
                            type="button"
                            className="danger-button small-button"
                            onClick={(event) => {
                              event.stopPropagation();
                              removeDocument(document);
                            }}
                          >
                            Delete
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>

          <section className="detail-grid">
            <article className="panel stack">
              <h3>Chunks {selectedDocument ? `for ${selectedDocument.name}` : ""}</h3>
              <div className="chunk-list">
                {chunks.map((chunk) => (
                  <div className="chunk-card" key={chunk.id}>
                    <div className="section-heading">
                      <strong>#{chunk.ordinal}</strong>
                      <span className="status-pill">{chunk.is_indexable ? "child" : "parent"}</span>
                    </div>
                    <p>{chunk.text}</p>
                    {chunk.parent_chunk_id ? <small>parent: {chunk.parent_chunk_id}</small> : null}
                  </div>
                ))}
                {chunks.length === 0 ? <p className="empty-state">No chunks loaded.</p> : null}
              </div>
            </article>

            <article className="panel stack">
              <div className="section-heading">
                <h3>Knowledge graph</h3>
                <form
                  className="inline-form"
                  onSubmit={(event) => {
                    event.preventDefault();
                    if (selectedCollectionId) refreshCollectionGraph(selectedCollectionId, entityFilter);
                  }}
                >
                  <input value={entityFilter} onChange={(event) => setEntityFilter(event.target.value)} placeholder="Entity" />
                  <button className="secondary-button" type="submit">
                    Filter
                  </button>
                </form>
              </div>
              <div className="graph-list">
                {triples.map((triple) => (
                  <div className="graph-row" key={triple.id}>
                    <strong>{triple.subject}</strong>
                    <span>{triple.predicate}</span>
                    <strong>{triple.object}</strong>
                    <small>{triple.confidence.toFixed(2)}</small>
                  </div>
                ))}
                {triples.length === 0 ? <p className="empty-state">No graph triples yet.</p> : null}
              </div>
            </article>
          </section>
        </main>
      </div>
    </section>
  );
}

function toMessage(error: unknown) {
  return error instanceof Error ? error.message : "Request failed.";
}

function isTerminalStatus(status: Document["status"]) {
  return status === "READY" || status === "FAILED" || status === "CANCELLED";
}
