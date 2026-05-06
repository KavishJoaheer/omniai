import { FormEvent, useEffect, useState } from "react";

import {
  ApiError,
  ApiKeyCreated,
  ApiKeySummary,
  AuditEvent,
  Collection,
  Document,
  Provider,
  Team,
  TenantInfo,
  UserSummary,
  api
} from "../../api/client";
import { useToast } from "../../components/Toast";
import { Skeleton, SkeletonCard, SkeletonTable } from "../../components/Skeleton";
import { HelpTip } from "../../components/Tooltip";

interface AdminPageProps {
  /** Called after provider list changes so App can update the LLM indicator. */
  onProvidersChange?: (providers: Provider[]) => void;
}

// Pre-filled provider templates so admins know what values to use
const PROVIDER_TEMPLATES: Record<string, { baseUrl: string; model: string }> = {
  openai:    { baseUrl: "https://api.openai.com/v1",       model: "gpt-4o-mini" },
  anthropic: { baseUrl: "https://api.anthropic.com",       model: "claude-3-5-sonnet-20241022" },
  gemini:    { baseUrl: "https://generativelanguage.googleapis.com/v1beta", model: "gemini-1.5-flash" },
  ollama:    { baseUrl: "http://localhost:11434",          model: "llama3.2" },
  cohere:    { baseUrl: "https://api.cohere.ai/v1",        model: "command-r" },
};

export function AdminPage({ onProvidersChange }: AdminPageProps) {
  const { toast } = useToast();

  const [tenant, setTenant]             = useState<TenantInfo | null>(null);
  const [teams, setTeams]               = useState<Team[]>([]);
  const [users, setUsers]               = useState<UserSummary[]>([]);
  const [auditEvents, setAuditEvents]   = useState<AuditEvent[]>([]);
  const [apiKeys, setApiKeys]           = useState<ApiKeySummary[]>([]);
  const [collections, setCollections]   = useState<Collection[]>([]);
  const [documents, setDocuments]       = useState<Document[]>([]);
  const [providers, setProviders]       = useState<Provider[]>([]);
  const [health, setHealth]             = useState("checking");
  const [createdKey, setCreatedKey]     = useState<ApiKeyCreated | null>(null);
  const [keyName, setKeyName]           = useState("");
  const [busy, setBusy]                 = useState(false);
  const [error, setError]               = useState("");
  const [initialLoading, setInitialLoading] = useState(true);

  // Provider form
  const [providerKind, setProviderKind]   = useState("llm");
  const [providerName, setProviderName]   = useState("");
  const [providerBaseUrl, setProviderBaseUrl] = useState("");
  const [providerModel, setProviderModel] = useState("");
  const [providerApiKey, setProviderApiKey] = useState("");
  const [providerEnabled, setProviderEnabled] = useState(true);

  useEffect(() => { refresh().finally(() => setInitialLoading(false)); }, []);

  async function refresh() {
    setError("");
    const [tenantR, teamR, userR, auditR, keyR, providerR, collectionR, healthR] =
      await Promise.allSettled([
        api.tenant(), api.teams(), api.users(), api.auditEvents(),
        api.apiKeys(), api.providers(), api.listCollections(), api.health(),
      ]);

    if (tenantR.status    === "fulfilled") setTenant(tenantR.value);
    if (teamR.status      === "fulfilled") setTeams(teamR.value);
    if (userR.status      === "fulfilled") setUsers(userR.value);
    if (auditR.status     === "fulfilled") setAuditEvents(auditR.value);
    if (keyR.status       === "fulfilled") setApiKeys(keyR.value);
    if (healthR.status    === "fulfilled") setHealth(healthR.value.status);

    if (providerR.status === "fulfilled") {
      setProviders(providerR.value);
      onProvidersChange?.(providerR.value);
    }

    if (collectionR.status === "fulfilled") {
      setCollections(collectionR.value);
      const docResults = await Promise.allSettled(
        collectionR.value.map((c) => api.listDocuments(c.id))
      );
      setDocuments(docResults.flatMap((r) => (r.status === "fulfilled" ? r.value : [])));
    }

    const failed = [tenantR, teamR, userR, auditR, keyR, providerR, collectionR, healthR]
      .find((r) => r.status === "rejected");
    if (failed?.status === "rejected") setError(toErrorMessage(failed.reason));
  }

  const storageBytes      = documents.reduce((n, d) => n + d.size_bytes, 0);
  const enabledProviders  = providers.filter((p) => p.enabled);
  const llmProvider       = enabledProviders.find((p) => p.kind === "llm");
  const embeddingProvider = enabledProviders.find((p) => p.kind === "embedding");
  const rerankerProvider  = enabledProviders.find((p) => p.kind === "reranker");

  // Auto-fill template when user types a known provider name
  function handleProviderNameChange(value: string) {
    setProviderName(value);
    const tpl = PROVIDER_TEMPLATES[value.toLowerCase()];
    if (tpl) {
      setProviderBaseUrl(tpl.baseUrl);
      setProviderModel(tpl.model);
    }
  }

  async function createKey(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!keyName.trim()) return;
    setBusy(true); setError("");
    try {
      const created = await api.createApiKey(keyName, ["tenant:read", "collections:write", "documents:write"]);
      setCreatedKey(created);
      setKeyName("");
      toast("API key created — copy it now, it won't be shown again.", "success");
      await refresh();
    } catch (caught) {
      const msg = toErrorMessage(caught);
      setError(msg);
      toast(msg, "error");
    } finally { setBusy(false); }
  }

  async function revokeKey(id: string) {
    setBusy(true); setError("");
    try {
      await api.revokeApiKey(id);
      toast("API key revoked.", "info");
      await refresh();
    } catch (caught) {
      const msg = toErrorMessage(caught);
      setError(msg); toast(msg, "error");
    } finally { setBusy(false); }
  }

  async function createProvider(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!providerName.trim()) return;
    setBusy(true); setError("");
    try {
      await api.createProvider({
        kind: providerKind,
        name: providerName.trim(),
        base_url: providerBaseUrl.trim() || null,
        default_model: providerModel.trim() || null,
        api_key: providerApiKey || null,
        enabled: providerEnabled,
      });
      setProviderName(""); setProviderBaseUrl(""); setProviderModel("");
      setProviderApiKey(""); setProviderEnabled(true);
      toast(`Provider "${providerName}" added${providerEnabled ? " and enabled" : ""}.`, "success");
      await refresh();
    } catch (caught) {
      const msg = toErrorMessage(caught);
      setError(msg); toast(msg, "error");
    } finally { setBusy(false); }
  }

  async function toggleProvider(provider: Provider) {
    setBusy(true); setError("");
    try {
      const updated = await api.updateProvider(provider.id, { enabled: !provider.enabled });
      setProviders((cur) => cur.map((p) => (p.id === updated.id ? updated : p)));
      onProvidersChange?.(providers.map((p) => (p.id === updated.id ? updated : p)));
      toast(`${provider.name} ${updated.enabled ? "enabled" : "disabled"}.`, "info");
    } catch (caught) {
      const msg = toErrorMessage(caught);
      setError(msg); toast(msg, "error");
    } finally { setBusy(false); }
  }

  async function deleteProvider(provider: Provider) {
    if (!window.confirm(`Delete provider "${provider.name}"? This cannot be undone.`)) return;
    setBusy(true); setError("");
    try {
      await api.deleteProvider(provider.id);
      const next = providers.filter((p) => p.id !== provider.id);
      setProviders(next);
      onProvidersChange?.(next);
      toast(`Provider "${provider.name}" deleted.`, "info");
    } catch (caught) {
      const msg = toErrorMessage(caught);
      setError(msg); toast(msg, "error");
    } finally { setBusy(false); }
  }

  // ── Render ────────────────────────────────────────────────────────────────────

  return (
    <section className="page">
      <header className="page-header">
        <div>
          <p className="eyebrow">Admin Dashboard</p>
          <h2>Operations &amp; governance</h2>
        </div>
        <button className="secondary-button" type="button" onClick={refresh} disabled={busy}>
          Refresh
        </button>
      </header>

      {error ? <p className="alert" role="alert">{error}</p> : null}

      {/* ── Provider setup callout (most important for new admins) ── */}
      {!initialLoading && enabledProviders.length === 0 && (
        <div className="setup-banner setup-banner-warning" role="status">
          <div className="setup-banner-icon">⚠</div>
          <div className="setup-banner-body">
            <strong>No AI provider enabled yet</strong>
            <span>
              Chat and Agents require an LLM provider. Add one below — for a
              quick start, type <code>openai</code>, <code>anthropic</code>, or{" "}
              <code>ollama</code> as the Name and the form pre-fills automatically.
            </span>
          </div>
        </div>
      )}

      {/* ── Metric cards ── */}
      <div className="summary-grid">
        {initialLoading ? (
          <><SkeletonCard /><SkeletonCard /><SkeletonCard /><SkeletonCard /></>
        ) : (
          <>
            <article className="metric-card">
              <span>Tenant</span>
              <strong>{tenant?.name || "-"}</strong>
            </article>
            <article className="metric-card">
              <span>Members</span>
              <strong>{tenant?.memberCount ?? users.length}</strong>
            </article>
            <article className="metric-card">
              <span>Teams</span>
              <strong>{tenant?.teamCount ?? teams.length}</strong>
            </article>
            <article className="metric-card">
              <span>Backend health</span>
              <strong className={health === "healthy" || health === "ok" ? "text-success" : "text-danger"}>
                {health}
              </strong>
            </article>
          </>
        )}
      </div>
      <div className="summary-grid">
        {initialLoading ? (
          <><SkeletonCard /><SkeletonCard /><SkeletonCard /><SkeletonCard /></>
        ) : (
          <>
            <article className="metric-card">
              <span>Collections</span>
              <strong>{collections.length}</strong>
            </article>
            <article className="metric-card">
              <span>Documents</span>
              <strong>{documents.length}</strong>
            </article>
            <article className="metric-card">
              <span>Storage used</span>
              <strong>{formatBytes(storageBytes)}</strong>
            </article>
            <article className="metric-card">
              <span>Enabled providers</span>
              <strong className={enabledProviders.length === 0 ? "text-danger" : "text-success"}>
                {enabledProviders.length}
              </strong>
            </article>
          </>
        )}
      </div>

      {/* ── Provider section ── */}
      <section className="panel stack">
        <h3>AI Providers</h3>
        <p className="muted" style={{ marginTop: 0 }}>
          Providers connect Omni-AI to AI models. You need at least one{" "}
          <strong>LLM</strong> provider enabled for Chat and Agents to work.
        </p>

        {/* Current provider status */}
        <div className="detail-grid">
          <article className={`metric-card ${llmProvider ? "" : "metric-card-warn"}`}>
            <span>
              LLM <HelpTip text="Used for Chat answers and Agent steps. Required." />
            </span>
            <strong>{llmProvider ? providerLabel(llmProvider) : "⚠ Not configured"}</strong>
          </article>
          <article className="metric-card">
            <span>
              Embedding <HelpTip text="Converts text to vectors for search. Uses Ollama nomic-embed-text by default." />
            </span>
            <strong>{embeddingProvider ? providerLabel(embeddingProvider) : "Default (built-in)"}</strong>
          </article>
          <article className="metric-card">
            <span>
              Reranker <HelpTip text="Re-orders search results by relevance. Improves answer quality. Optional." />
            </span>
            <strong>{rerankerProvider ? providerLabel(rerankerProvider) : "paired/local"}</strong>
          </article>
        </div>

        {/* Quick-start guide */}
        <details className="provider-guide">
          <summary>Quick start — which provider should I add?</summary>
          <div className="provider-guide-body">
            <div className="provider-option">
              <strong>OpenAI (recommended for most users)</strong>
              <span>Get an API key from <a href="https://platform.openai.com/api-keys" target="_blank" rel="noreferrer">platform.openai.com</a>. Type <code>openai</code> as the Name below.</span>
            </div>
            <div className="provider-option">
              <strong>Anthropic Claude</strong>
              <span>Get an API key from <a href="https://console.anthropic.com/" target="_blank" rel="noreferrer">console.anthropic.com</a>. Type <code>anthropic</code> as the Name.</span>
            </div>
            <div className="provider-option">
              <strong>Ollama (free, runs on your machine)</strong>
              <span>Install from <a href="https://ollama.com" target="_blank" rel="noreferrer">ollama.com</a>, then run <code>ollama pull llama3.2</code>. Type <code>ollama</code> as the Name — no API key needed.</span>
            </div>
          </div>
        </details>

        {/* Add provider form */}
        <form className="stack provider-form" onSubmit={createProvider}>
          <h4>Add a provider</h4>
          <div className="control-grid">
            <label>
              Kind <HelpTip text="LLM = language model for chat. Embedding = text-to-vector for search." />
              <select value={providerKind} onChange={(e) => setProviderKind(e.target.value)}>
                <option value="llm">LLM (chat &amp; agents)</option>
                <option value="embedding">Embedding (search)</option>
                <option value="reranker">Reranker (result quality)</option>
                <option value="asr">ASR (speech-to-text)</option>
                <option value="tts">TTS (text-to-speech)</option>
              </select>
            </label>
            <label>
              Name <HelpTip text="Type openai, anthropic, gemini, or ollama to auto-fill the URL and model." />
              <input
                value={providerName}
                onChange={(e) => handleProviderNameChange(e.target.value)}
                placeholder="e.g. openai, anthropic, ollama"
                required
                list="provider-name-suggestions"
              />
              <datalist id="provider-name-suggestions">
                <option value="openai" />
                <option value="anthropic" />
                <option value="gemini" />
                <option value="ollama" />
                <option value="cohere" />
              </datalist>
            </label>
            <label>
              Base URL <HelpTip text="The API endpoint. Auto-filled when you type a known provider name." />
              <input
                value={providerBaseUrl}
                onChange={(e) => setProviderBaseUrl(e.target.value)}
                placeholder="Auto-filled — or enter custom URL"
              />
            </label>
            <label>
              Default model <HelpTip text="Auto-filled. Can be changed later. Leave blank to let the provider decide." />
              <input
                value={providerModel}
                onChange={(e) => setProviderModel(e.target.value)}
                placeholder="Auto-filled — or enter model name"
              />
            </label>
            <label>
              API key <HelpTip text="Stored encrypted. Never shown again after saving. Leave blank for Ollama." />
              <input
                value={providerApiKey}
                onChange={(e) => setProviderApiKey(e.target.value)}
                placeholder={providerName.toLowerCase() === "ollama" ? "Not required for Ollama" : "Paste your API key here"}
                type="password"
                autoComplete="off"
              />
            </label>
            <label className="inline-check">
              <input
                checked={providerEnabled}
                onChange={(e) => setProviderEnabled(e.target.checked)}
                type="checkbox"
              />
              Enable immediately after adding
            </label>
          </div>
          <button
            className="primary-button"
            disabled={busy || !providerName.trim()}
            type="submit"
          >
            {busy ? "Adding…" : "Add provider"}
          </button>
        </form>

        {/* Existing providers table */}
        {initialLoading ? (
          <SkeletonTable rows={2} cols={6} />
        ) : (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th scope="col">Kind</th>
                  <th scope="col">Name</th>
                  <th scope="col">Default model</th>
                  <th scope="col">Status</th>
                  <th scope="col">Credentials</th>
                  <th scope="col"></th>
                </tr>
              </thead>
              <tbody>
                {providers.map((provider) => (
                  <tr key={provider.id}>
                    <td><span className="kind-badge">{provider.kind}</span></td>
                    <td>{provider.name}</td>
                    <td>{provider.defaultModel || <span className="muted">—</span>}</td>
                    <td>
                      <span className={`status-pill ${provider.enabled ? "ready" : ""}`}>
                        {provider.enabled ? "Enabled" : "Disabled"}
                      </span>
                    </td>
                    <td>{provider.hasCredentials ? "Stored ✓" : <span className="muted">—</span>}</td>
                    <td>
                      <div className="button-row">
                        <button
                          className="secondary-button small-button"
                          disabled={busy}
                          onClick={() => toggleProvider(provider)}
                          type="button"
                        >
                          {provider.enabled ? "Disable" : "Enable"}
                        </button>
                        <button
                          className="danger-button small-button"
                          disabled={busy}
                          onClick={() => deleteProvider(provider)}
                          type="button"
                        >
                          Delete
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            {providers.length === 0 && (
              <p className="empty-state">
                No providers yet. Add one above to enable Chat and Agents.
              </p>
            )}
          </div>
        )}
      </section>

      {/* ── API Keys ── */}
      <div className="detail-grid">
        <section className="panel stack">
          <h3>API Keys</h3>
          <p className="muted" style={{ marginTop: 0 }}>
            Use API keys to access Omni-AI from scripts or integrations
            without logging in. Keys start with <code>omsk_</code>.
          </p>
          <form className="inline-form" onSubmit={createKey}>
            <input
              value={keyName}
              onChange={(e) => setKeyName(e.target.value)}
              placeholder="Key name, e.g. CI Pipeline"
            />
            <button className="primary-button" type="submit" disabled={busy || !keyName.trim()}>
              Create
            </button>
          </form>
          {createdKey && (
            <div className="token-box" role="alert">
              <strong>Copy this key now — it won't be shown again!</strong>
              <code style={{ wordBreak: "break-all" }}>{createdKey.token}</code>
              <button
                type="button"
                className="secondary-button small-button"
                onClick={() => { navigator.clipboard.writeText(createdKey.token); toast("Copied!", "success"); }}
              >
                Copy
              </button>
            </div>
          )}
          {initialLoading ? (
            <SkeletonTable rows={3} cols={3} />
          ) : (
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th scope="col">Name</th>
                    <th scope="col">Prefix</th>
                    <th scope="col">Status</th>
                    <th scope="col"></th>
                  </tr>
                </thead>
                <tbody>
                  {apiKeys.map((key) => (
                    <tr key={key.id}>
                      <td>{key.name}</td>
                      <td><code>{key.prefix}</code></td>
                      <td>
                        <span className={`status-pill ${key.revokedAt ? "" : "ready"}`}>
                          {key.revokedAt ? "Revoked" : "Active"}
                        </span>
                      </td>
                      <td>
                        <button
                          className="secondary-button small-button"
                          disabled={busy || Boolean(key.revokedAt)}
                          onClick={() => revokeKey(key.id)}
                          type="button"
                        >
                          Revoke
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {apiKeys.length === 0 && (
                <p className="empty-state">
                  No API keys yet. Create one above to use the API programmatically.
                </p>
              )}
            </div>
          )}
        </section>

        {/* ── Users ── */}
        <section className="panel stack">
          <h3>Users</h3>
          {initialLoading ? (
            <SkeletonTable rows={3} cols={3} />
          ) : (
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th scope="col">User</th>
                    <th scope="col">Role</th>
                    <th scope="col">Status</th>
                  </tr>
                </thead>
                <tbody>
                  {users.map((user) => (
                    <tr key={user.id}>
                      <td>
                        <strong>{user.displayName}</strong>
                        <small>{user.email}</small>
                      </td>
                      <td>{user.role}</td>
                      <td>
                        <span className={`status-pill ${user.isActive ? "ready" : ""}`}>
                          {user.isActive ? "Active" : "Disabled"}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {users.length === 0 && (
                <p className="empty-state">No users data available.</p>
              )}
            </div>
          )}
        </section>
      </div>

      {/* ── Teams ── */}
      <section className="panel stack">
        <h3>Teams</h3>
        {initialLoading ? (
          <SkeletonTable rows={2} cols={3} />
        ) : (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th scope="col">Name</th>
                  <th scope="col">Members</th>
                  <th scope="col">Your role</th>
                </tr>
              </thead>
              <tbody>
                {teams.map((team) => (
                  <tr key={team.id}>
                    <td>
                      <strong>{team.name}</strong>
                      {team.description && <small>{team.description}</small>}
                    </td>
                    <td>{team.memberCount ?? 0}</td>
                    <td>{team.myRole || <span className="muted">—</span>}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            {teams.length === 0 && (
              <p className="empty-state">No teams yet.</p>
            )}
          </div>
        )}
      </section>

      {/* ── Audit events ── */}
      <section className="panel stack">
        <h3>
          Audit Log <HelpTip text="Every significant action is recorded here: logins, uploads, deletions, config changes." />
        </h3>
        {initialLoading ? (
          <SkeletonTable rows={5} cols={3} />
        ) : (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th scope="col">Action</th>
                  <th scope="col">Target</th>
                  <th scope="col">When</th>
                </tr>
              </thead>
              <tbody>
                {auditEvents.map((event) => (
                  <tr key={event.id}>
                    <td><code>{event.action}</code></td>
                    <td>{event.targetType} / {event.targetId}</td>
                    <td>{formatDate(event.createdAt)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            {auditEvents.length === 0 && (
              <p className="empty-state">No audit events yet.</p>
            )}
          </div>
        )}
      </section>
    </section>
  );
}

// ── Helpers ────────────────────────────────────────────────────────────────────

function toErrorMessage(error: unknown) {
  return error instanceof ApiError ? error.message : "Request failed.";
}

function formatDate(value: string) {
  return new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short" })
    .format(new Date(value));
}

function formatBytes(value: number) {
  if (value < 1024) return `${value} B`;
  const units = ["KB", "MB", "GB", "TB"];
  let amount = value / 1024, index = 0;
  while (amount >= 1024 && index < units.length - 1) { amount /= 1024; index++; }
  return `${amount.toFixed(amount >= 10 ? 0 : 1)} ${units[index]}`;
}

function providerLabel(p: Provider) {
  return p.defaultModel ? `${p.name} / ${p.defaultModel}` : p.name;
}
