import { FormEvent, useEffect, useState } from "react";
import { Collection, Deployment, SandboxResult, api } from "../../api/client";

const STARTER_CODE = `# Sandbox demo -- Python runs in a confined subprocess
# No secrets from the host process leak in here.
import sys, os, math

print("Hello from the Omni-AI Sandbox!")
print(f"Python {sys.version.split()[0]}")

# No env vars from the host leak in
secret = os.environ.get("ENCRYPTION_KEY", "NOT_FOUND")
print(f"ENCRYPTION_KEY visible: {secret}")

# Write an artifact -- any file written here is returned
with open("result.txt", "w") as f:
    f.write(f"pi = {math.pi}\\n")
    f.write("Sandbox artifact collected successfully.\\n")

print("Done.")
`;

export function DeploymentsPage() {
  const [deployments, setDeployments] = useState<Deployment[]>([]);
  const [collections, setCollections] = useState<Collection[]>([]);
  const [selectedId, setSelectedId] = useState("");

  // Create form
  const [newName, setNewName] = useState("");
  const [newSlug, setNewSlug] = useState("");
  const [newTargetId, setNewTargetId] = useState("");
  const [newQuota, setNewQuota] = useState(200);
  const [newAnon, setNewAnon] = useState(true);

  // Sandbox panel
  const [code, setCode] = useState(STARTER_CODE);
  const [sandboxResult, setSandboxResult] = useState<SandboxResult | null>(null);
  const [sandboxRunning, setSandboxRunning] = useState(false);

  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  const selected = deployments.find((d) => d.id === selectedId) || null;

  useEffect(() => {
    refresh();
  }, []);

  async function refresh() {
    setError("");
    try {
      const [deps, cols] = await Promise.all([api.listDeployments(), api.listCollections()]);
      setDeployments(deps);
      setCollections(cols);
      if (!newTargetId && cols.length > 0) setNewTargetId(cols[0].id);
    } catch (e) {
      setError(msg(e));
    }
  }

  async function create(e: FormEvent) {
    e.preventDefault();
    if (!newName.trim() || !newTargetId) return;
    setBusy(true);
    setError("");
    setNotice("");
    try {
      const dep = await api.createDeployment({
        name: newName.trim(),
        slug: newSlug.trim() || undefined,
        kind: "public_chat",
        target_kind: "collection",
        target_id: newTargetId,
        anonymous_allowed: newAnon,
        daily_message_quota: newQuota,
      });
      setNewName("");
      setNewSlug("");
      setNotice(`Deployment "${dep.name}" published at /c/${dep.slug}`);
      await refresh();
      setSelectedId(dep.id);
    } catch (e) {
      setError(msg(e));
    } finally {
      setBusy(false);
    }
  }

  async function toggleStatus(dep: Deployment) {
    setBusy(true);
    setError("");
    try {
      const updated = await api.updateDeployment(dep.id, {
        status: dep.status === "ACTIVE" ? "PAUSED" : "ACTIVE",
      });
      setDeployments((prev) => prev.map((d) => (d.id === updated.id ? updated : d)));
      if (selectedId === updated.id) setSelectedId(updated.id);
    } catch (e) {
      setError(msg(e));
    } finally {
      setBusy(false);
    }
  }

  async function remove(dep: Deployment) {
    if (!window.confirm(`Delete deployment "${dep.name}"?`)) return;
    setBusy(true);
    setError("");
    try {
      await api.deleteDeployment(dep.id);
      setDeployments((prev) => prev.filter((d) => d.id !== dep.id));
      if (selectedId === dep.id) setSelectedId("");
      setNotice("Deployment deleted.");
    } catch (e) {
      setError(msg(e));
    } finally {
      setBusy(false);
    }
  }

  async function runSandbox() {
    setSandboxRunning(true);
    setSandboxResult(null);
    setError("");
    try {
      const result = await api.runSandbox(code, 10);
      setSandboxResult(result);
    } catch (e) {
      setError(msg(e));
    } finally {
      setSandboxRunning(false);
    }
  }

  return (
    <section className="page">
      <header className="page-header">
        <div>
          <p className="eyebrow">Publish &amp; Execute</p>
          <h2>Deploy Manager &amp; Sandbox</h2>
        </div>
        <button className="secondary-button" type="button" onClick={refresh}>
          Refresh
        </button>
      </header>

      {error ? <p className="alert">{error}</p> : null}
      {notice ? <p className="notice">{notice}</p> : null}

      {/* ── Two-column layout ───────────────────────────────────────────── */}
      <div className="workspace-grid">

        {/* ── LEFT: Deploy Manager ────────────────────────────────────── */}
        <aside className="panel stack">
          <h3>New deployment</h3>
          <form className="stack" onSubmit={create}>
            <label>
              Name
              <input value={newName} onChange={(e) => setNewName(e.target.value)} required placeholder="My public chat" />
            </label>
            <label>
              Slug (optional)
              <input value={newSlug} onChange={(e) => setNewSlug(e.target.value)} placeholder="auto-generated" />
            </label>
            <label>
              Target collection
              <select value={newTargetId} onChange={(e) => setNewTargetId(e.target.value)}>
                {collections.map((c) => (
                  <option key={c.id} value={c.id}>{c.name}</option>
                ))}
              </select>
            </label>
            <label>
              Daily message quota
              <input type="number" min={0} value={newQuota} onChange={(e) => setNewQuota(Number(e.target.value))} />
            </label>
            <label className="inline-check">
              <input type="checkbox" checked={newAnon} onChange={(e) => setNewAnon(e.target.checked)} />
              Allow anonymous users
            </label>
            <button className="primary-button" type="submit" disabled={busy || !newName.trim()}>
              Publish
            </button>
          </form>

          <div className="stack">
            <h3>Active deployments</h3>
            {deployments.length === 0 ? (
              <p className="empty-state">No deployments yet.</p>
            ) : (
              deployments.map((dep) => (
                <button
                  key={dep.id}
                  type="button"
                  className={dep.id === selectedId ? "list-row selected" : "list-row"}
                  onClick={() => setSelectedId(dep.id)}
                >
                  <span>
                    <strong>{dep.name}</strong>
                    <small>/c/{dep.slug}</small>
                  </span>
                  <span className={`status-pill ${dep.status === "ACTIVE" ? "ready" : ""}`}>
                    {dep.status}
                  </span>
                </button>
              ))
            )}
          </div>
        </aside>

        {/* ── RIGHT: Detail + Sandbox ──────────────────────────────────── */}
        <main className="stack">

          {/* Deployment detail */}
          {selected ? (
            <section className="panel stack">
              <div className="section-heading">
                <div>
                  <h3>{selected.name}</h3>
                  <p>Published collection deployment</p>
                </div>
                <div className="button-row">
                  <button
                    className="secondary-button"
                    type="button"
                    onClick={() => toggleStatus(selected)}
                    disabled={busy}
                  >
                    {selected.status === "ACTIVE" ? "Pause" : "Resume"}
                  </button>
                  <button
                    className="danger-button"
                    type="button"
                    onClick={() => remove(selected)}
                    disabled={busy}
                  >
                    Delete
                  </button>
                </div>
              </div>

              <div className="control-grid">
                <div>
                  <p className="eyebrow">Public URL</p>
                  <a
                    href={`/c/${selected.slug}/info`}
                    target="_blank"
                    rel="noreferrer"
                    className="code-link"
                  >
                    /c/{selected.slug}
                  </a>
                </div>
                <div>
                  <p className="eyebrow">Status</p>
                  <span className={`status-pill ${selected.status === "ACTIVE" ? "ready" : ""}`}>
                    {selected.status}
                  </span>
                </div>
                <div>
                  <p className="eyebrow">Today / Quota</p>
                  <strong>{selected.today_message_count} / {selected.daily_message_quota || "unlimited"}</strong>
                </div>
                <div>
                  <p className="eyebrow">Total messages</p>
                  <strong>{selected.message_count}</strong>
                </div>
                <div>
                  <p className="eyebrow">Anonymous access</p>
                  <strong>{selected.anonymous_allowed ? "Yes" : "No"}</strong>
                </div>
                <div>
                  <p className="eyebrow">Target</p>
                  <strong>{selected.target_kind} {selected.target_id.slice(0, 12)}…</strong>
                </div>
              </div>

              <div>
                <p className="eyebrow">Test the public chat endpoint</p>
                <p style={{ fontSize: "0.85em", color: "var(--muted)" }}>
                  Click below — this URL is accessible without logging in:
                </p>
                <a
                  href={`/c/${selected.slug}/info`}
                  target="_blank"
                  rel="noreferrer"
                >
                  <button className="primary-button" type="button">
                    Open /c/{selected.slug}/info
                  </button>
                </a>
              </div>
            </section>
          ) : (
            <section className="panel">
              <p className="empty-state">Select or create a deployment to see details.</p>
            </section>
          )}

          {/* Sandbox panel */}
          <section className="panel stack">
            <div className="section-heading">
              <div>
                <h3>Python Sandbox</h3>
                <p>
                  Code runs in a confined subprocess — scrubbed environment, fresh tempdir,
                  enforced timeout. Used internally by agent code nodes.
                </p>
              </div>
              <span className="status-pill ready">subprocess</span>
            </div>

            <label>
              Python code
              <textarea
                value={code}
                onChange={(e) => setCode(e.target.value)}
                rows={12}
                style={{ fontFamily: "monospace", fontSize: "0.85em" }}
              />
            </label>

            <button
              className="primary-button"
              type="button"
              onClick={runSandbox}
              disabled={sandboxRunning || !code.trim()}
            >
              {sandboxRunning ? "Running..." : "Run in Sandbox"}
            </button>

            {sandboxResult ? (
              <div className="stack">
                <div className="section-heading">
                  <div>
                    <h4>Result</h4>
                    <p>exit {sandboxResult.exit_code} &middot; {sandboxResult.duration_seconds}s{sandboxResult.timed_out ? " (TIMED OUT)" : ""}</p>
                  </div>
                  <span className={`status-pill ${sandboxResult.exit_code === 0 ? "ready" : ""}`}>
                    {sandboxResult.exit_code === 0 ? "success" : "error"}
                  </span>
                </div>

                {sandboxResult.stdout ? (
                  <div>
                    <p className="eyebrow">stdout</p>
                    <pre className="content-preview">{sandboxResult.stdout}</pre>
                  </div>
                ) : null}

                {sandboxResult.stderr ? (
                  <div>
                    <p className="eyebrow">stderr</p>
                    <pre className="content-preview" style={{ color: "var(--danger, #e74c3c)" }}>
                      {sandboxResult.stderr}
                    </pre>
                  </div>
                ) : null}

                {Object.keys(sandboxResult.artifacts).length > 0 ? (
                  <div>
                    <p className="eyebrow">Artifacts written by code</p>
                    {Object.entries(sandboxResult.artifacts).map(([path, content]) => (
                      <div key={path}>
                        <strong>{path}</strong>
                        <pre className="content-preview">{content}</pre>
                      </div>
                    ))}
                  </div>
                ) : null}
              </div>
            ) : null}
          </section>
        </main>
      </div>
    </section>
  );
}

function msg(e: unknown): string {
  return e instanceof Error ? e.message : "Request failed.";
}
