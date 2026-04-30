import { FormEvent, useEffect, useState } from "react";
import { NavLink, Route, Routes } from "react-router-dom";

import { HomePage } from "../features/home/HomePage";
import { KnowledgePage } from "../features/knowledge/KnowledgePage";
import { ChatPage } from "../features/chat/ChatPage";
import { AgentsPage } from "../features/agents/AgentsPage";
import { SearchPage } from "../features/search/SearchPage";
import { AdminPage } from "../features/admin/AdminPage";
import { DeploymentsPage } from "../features/deployments/DeploymentsPage";
import { ApiError, Principal, api } from "../api/client";

const navItems = [
  { to: "/", label: "Overview" },
  { to: "/knowledge", label: "Knowledge" },
  { to: "/chat", label: "Chat" },
  { to: "/agents", label: "Agents" },
  { to: "/search", label: "Search" },
  { to: "/deploy", label: "Deploy" },
  { to: "/admin", label: "Admin" }
];

export function App() {
  const [principal, setPrincipal] = useState<Principal | null>(null);
  const [loading, setLoading] = useState(true);
  const [authError, setAuthError] = useState("");

  useEffect(() => {
    api
      .me()
      .then(setPrincipal)
      .catch(() => setPrincipal(null))
      .finally(() => setLoading(false));
  }, []);

  if (loading) {
    return (
      <main className="auth-screen">
        <section className="panel auth-panel">
          <p className="eyebrow">Omni-AI</p>
          <h1>Loading workspace</h1>
        </section>
      </main>
    );
  }

  if (!principal) {
    return (
      <LoginScreen
        error={authError}
        onLogin={async (email, password) => {
          setAuthError("");
          try {
            const result = await api.login(email, password);
            setPrincipal(result.principal);
          } catch (error) {
            setAuthError(error instanceof ApiError ? error.message : "Login failed.");
          }
        }}
      />
    );
  }

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div>
          <p className="eyebrow">Omni-AI</p>
          <h1>Omni-AI</h1>
          <p className="muted">{principal.tenantName}</p>
        </div>
        <nav className="nav-list" aria-label="Primary">
          {navItems.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.to === "/"}
              className={({ isActive }) => (isActive ? "nav-link active" : "nav-link")}
            >
              {item.label}
            </NavLink>
          ))}
        </nav>
        <div className="user-card">
          <strong>{principal.displayName}</strong>
          <span>{principal.email}</span>
          <span>{principal.role}</span>
          <button
            className="secondary-button"
            type="button"
            onClick={async () => {
              await api.logout();
              setPrincipal(null);
            }}
          >
            Sign out
          </button>
        </div>
      </aside>
      <main className="content">
        <Routes>
          <Route path="/" element={<HomePage />} />
          <Route path="/knowledge" element={<KnowledgePage />} />
          <Route path="/chat" element={<ChatPage />} />
          <Route path="/agents" element={<AgentsPage />} />
          <Route path="/search" element={<SearchPage />} />
          <Route path="/deploy" element={<DeploymentsPage />} />
          <Route path="/admin" element={<AdminPage />} />
        </Routes>
      </main>
    </div>
  );
}

function LoginScreen({
  error,
  onLogin
}: {
  error: string;
  onLogin: (email: string, password: string) => Promise<void>;
}) {
  const [email, setEmail] = useState("admin@omniai.local");
  const [password, setPassword] = useState("Admin12345!");
  const [submitting, setSubmitting] = useState(false);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSubmitting(true);
    try {
      await onLogin(email, password);
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <main className="auth-screen">
      <form className="panel auth-panel" onSubmit={submit}>
        <p className="eyebrow">Omni-AI Workspace</p>
        <h1>Sign in</h1>
        <label>
          Email
          <input value={email} onChange={(event) => setEmail(event.target.value)} type="email" required />
        </label>
        <label>
          Password
          <input
            autoComplete="current-password"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            type="password"
            required
          />
        </label>
        {error ? <p className="alert">{error}</p> : null}
        <button className="primary-button" type="submit" disabled={submitting}>
          {submitting ? "Signing in" : "Sign in"}
        </button>
      </form>
    </main>
  );
}

