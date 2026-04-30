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

export function AdminPage() {
  const [tenant, setTenant] = useState<TenantInfo | null>(null);
  const [teams, setTeams] = useState<Team[]>([]);
  const [users, setUsers] = useState<UserSummary[]>([]);
  const [auditEvents, setAuditEvents] = useState<AuditEvent[]>([]);
  const [apiKeys, setApiKeys] = useState<ApiKeySummary[]>([]);
  const [collections, setCollections] = useState<Collection[]>([]);
  const [documents, setDocuments] = useState<Document[]>([]);
  const [providers, setProviders] = useState<Provider[]>([]);
  const [health, setHealth] = useState("checking");
  const [createdKey, setCreatedKey] = useState<ApiKeyCreated | null>(null);
  const [keyName, setKeyName] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    refresh();
  }, []);

  async function refresh() {
    setError("");
    const [tenantResult, teamResult, userResult, auditResult, keyResult, providerResult, collectionResult, healthResult] =
      await Promise.allSettled([
      api.tenant(),
      api.teams(),
      api.users(),
      api.auditEvents(),
      api.apiKeys(),
      api.providers(),
      api.listCollections(),
      api.health()
    ]);

    if (tenantResult.status === "fulfilled") setTenant(tenantResult.value);
    if (teamResult.status === "fulfilled") setTeams(teamResult.value);
    if (userResult.status === "fulfilled") setUsers(userResult.value);
    if (auditResult.status === "fulfilled") setAuditEvents(auditResult.value);
    if (keyResult.status === "fulfilled") setApiKeys(keyResult.value);
    if (providerResult.status === "fulfilled") setProviders(providerResult.value);
    if (collectionResult.status === "fulfilled") {
      setCollections(collectionResult.value);
      const documentResults = await Promise.allSettled(
        collectionResult.value.map((collection) => api.listDocuments(collection.id))
      );
      setDocuments(documentResults.flatMap((result) => (result.status === "fulfilled" ? result.value : [])));
    }
    if (healthResult.status === "fulfilled") setHealth(healthResult.value.status);

    const failed = [tenantResult, teamResult, userResult, auditResult, keyResult, providerResult, collectionResult, healthResult].find(
      (result) => result.status === "rejected"
    );
    if (failed?.status === "rejected") {
      setError(toErrorMessage(failed.reason));
    }
  }

  const storageBytes = documents.reduce((total, document) => total + document.size_bytes, 0);
  const enabledProviders = providers.filter((provider) => provider.enabled);
  const llmProvider = enabledProviders.find((provider) => provider.kind === "llm");
  const embeddingProvider = enabledProviders.find((provider) => provider.kind === "embedding");
  const rerankerProvider = enabledProviders.find((provider) => provider.kind === "reranker");

  async function createKey(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!keyName.trim()) return;
    setBusy(true);
    setError("");
    try {
      const created = await api.createApiKey(keyName, ["tenant:read", "collections:write", "documents:write"]);
      setCreatedKey(created);
      setKeyName("");
      await refresh();
    } catch (caught) {
      setError(toErrorMessage(caught));
    } finally {
      setBusy(false);
    }
  }

  async function revokeKey(id: string) {
    setBusy(true);
    setError("");
    try {
      await api.revokeApiKey(id);
      await refresh();
    } catch (caught) {
      setError(toErrorMessage(caught));
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="page">
      <header className="page-header">
        <div>
          <p className="eyebrow">Admin Dashboard</p>
          <h2>Operations and governance</h2>
        </div>
        <button className="secondary-button" type="button" onClick={refresh} disabled={busy}>
          Refresh
        </button>
      </header>

      {error ? <p className="alert">{error}</p> : null}

      <div className="summary-grid">
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
          <span>Health</span>
          <strong>{health}</strong>
        </article>
      </div>

      <div className="summary-grid">
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
          <strong>{enabledProviders.length}</strong>
        </article>
      </div>

      <div className="detail-grid">
        <section className="panel stack">
          <h3>API keys</h3>
          <form className="inline-form" onSubmit={createKey}>
            <input value={keyName} onChange={(event) => setKeyName(event.target.value)} placeholder="Key name" />
            <button className="primary-button" type="submit" disabled={busy || !keyName.trim()}>
              Create
            </button>
          </form>
          {createdKey ? (
            <div className="token-box">
              <span>New token</span>
              <code>{createdKey.token}</code>
            </div>
          ) : null}
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Name</th>
                  <th>Prefix</th>
                  <th>Status</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {apiKeys.map((key) => (
                  <tr key={key.id}>
                    <td>{key.name}</td>
                    <td>{key.prefix}</td>
                    <td>{key.revokedAt ? "Revoked" : "Active"}</td>
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
            {apiKeys.length === 0 ? <p className="empty-state">No API keys yet.</p> : null}
          </div>
        </section>

        <section className="panel stack">
          <h3>Users</h3>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>User</th>
                  <th>Role</th>
                  <th>Status</th>
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
                    <td>{user.isActive ? "Active" : "Disabled"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            {users.length === 0 ? <p className="empty-state">No admin user data available.</p> : null}
          </div>
        </section>
      </div>

      <section className="panel stack">
        <h3>Provider status</h3>
        <div className="detail-grid">
          <article className="metric-card">
            <span>LLM</span>
            <strong>{llmProvider ? providerLabel(llmProvider) : "-"}</strong>
          </article>
          <article className="metric-card">
            <span>Embedding</span>
            <strong>{embeddingProvider ? providerLabel(embeddingProvider) : "-"}</strong>
          </article>
          <article className="metric-card">
            <span>Reranker</span>
            <strong>{rerankerProvider ? providerLabel(rerankerProvider) : "paired/local"}</strong>
          </article>
        </div>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Kind</th>
                <th>Name</th>
                <th>Default model</th>
                <th>Status</th>
              </tr>
            </thead>
            <tbody>
              {providers.map((provider) => (
                <tr key={provider.id}>
                  <td>{provider.kind}</td>
                  <td>{provider.name}</td>
                  <td>{provider.defaultModel || "-"}</td>
                  <td>{provider.enabled ? "Enabled" : "Disabled"}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {providers.length === 0 ? <p className="empty-state">No providers configured.</p> : null}
        </div>
      </section>

      <section className="panel stack">
        <h3>Teams</h3>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Name</th>
                <th>Members</th>
                <th>Role</th>
              </tr>
            </thead>
            <tbody>
              {teams.map((team) => (
                <tr key={team.id}>
                  <td>
                    <strong>{team.name}</strong>
                    <small>{team.description || "No description"}</small>
                  </td>
                  <td>{team.memberCount ?? 0}</td>
                  <td>{team.myRole || "-"}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {teams.length === 0 ? <p className="empty-state">No teams available.</p> : null}
        </div>
      </section>

      <section className="panel stack">
        <h3>Audit events</h3>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Action</th>
                <th>Target</th>
                <th>Created</th>
              </tr>
            </thead>
            <tbody>
              {auditEvents.map((event) => (
                <tr key={event.id}>
                  <td>{event.action}</td>
                  <td>
                    {event.targetType} / {event.targetId}
                  </td>
                  <td>{formatDate(event.createdAt)}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {auditEvents.length === 0 ? <p className="empty-state">No audit events available.</p> : null}
        </div>
      </section>
    </section>
  );
}

function toErrorMessage(error: unknown) {
  return error instanceof ApiError ? error.message : "Request failed.";
}

function formatDate(value: string) {
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: "medium",
    timeStyle: "short"
  }).format(new Date(value));
}

function formatBytes(value: number) {
  if (value < 1024) return `${value} B`;
  const units = ["KB", "MB", "GB", "TB"];
  let amount = value / 1024;
  let index = 0;
  while (amount >= 1024 && index < units.length - 1) {
    amount /= 1024;
    index += 1;
  }
  return `${amount.toFixed(amount >= 10 ? 0 : 1)} ${units[index]}`;
}

function providerLabel(provider: Provider) {
  return provider.defaultModel ? `${provider.name}/${provider.defaultModel}` : provider.name;
}
