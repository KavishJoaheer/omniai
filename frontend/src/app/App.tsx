import { FormEvent, useEffect, useState } from "react";
import { NavLink, Route, Routes, useLocation } from "react-router-dom";

import { HomePage } from "../features/home/HomePage";
import { KnowledgePage } from "../features/knowledge/KnowledgePage";
import { ChatPage } from "../features/chat/ChatPage";
import { AgentsPage } from "../features/agents/AgentsPage";
import { SearchPage } from "../features/search/SearchPage";
import { AdminPage } from "../features/admin/AdminPage";
import { DeploymentsPage } from "../features/deployments/DeploymentsPage";
import { ApiError, Principal, Provider, api } from "../api/client";
import { CommandPalette } from "../components/CommandPalette";
import { ErrorBoundary } from "../components/ErrorBoundary";
import { ToastProvider } from "../components/Toast";
import { useI18n, setI18nStore } from "../i18n";

// ── Theme persistence ──────────────────────────────────────────────────────────

type Theme = "light" | "dark" | "system";

function getStoredTheme(): Theme {
  const v = localStorage.getItem("omniai_theme");
  if (v === "light" || v === "dark" || v === "system") return v;
  return "system";
}

function applyTheme(theme: Theme) {
  const root = document.documentElement;
  if (theme === "dark")       root.setAttribute("data-theme", "dark");
  else if (theme === "light") root.setAttribute("data-theme", "light");
  else                        root.removeAttribute("data-theme");
  localStorage.setItem("omniai_theme", theme);
}

// Apply before first render to prevent flash
applyTheme(getStoredTheme());

// ── Provider health context (passed down via props for simplicity) ─────────────

export interface AppContext {
  hasLLMProvider: boolean;
}

// ── App ────────────────────────────────────────────────────────────────────────

export function App() {
  const { t, locale, setLocale } = useI18n();
  const [principal, setPrincipal]   = useState<Principal | null>(null);
  const [loading, setLoading]        = useState(true);
  const [authError, setAuthError]    = useState("");
  const [theme, setThemeState]       = useState<Theme>(getStoredTheme);
  const [paletteOpen, setPaletteOpen] = useState(false);
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [providers, setProviders]    = useState<Provider[]>([]);
  const location = useLocation();

  // Publish i18n store for non-hook consumers
  useEffect(() => { setI18nStore({ t, locale }); }, [t, locale]);

  // Auth check on mount
  useEffect(() => {
    api.me()
      .then(setPrincipal)
      .catch(() => setPrincipal(null))
      .finally(() => setLoading(false));
  }, []);

  // Load provider status once logged in (so pages can show setup warnings)
  useEffect(() => {
    if (!principal) return;
    api.providers().then(setProviders).catch(() => {});
  }, [principal]);

  // Close sidebar on navigation (mobile)
  useEffect(() => { setSidebarOpen(false); }, [location.pathname]);

  // Global ⌘+K / Ctrl+K
  useEffect(() => {
    function onKeyDown(e: KeyboardEvent) {
      if ((e.metaKey || e.ctrlKey) && e.key === "k") {
        e.preventDefault();
        setPaletteOpen((v) => !v);
      }
      if (e.key === "Escape") setSidebarOpen(false);
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, []);

  function cycleTheme() {
    const next: Theme = theme === "system" ? "light" : theme === "light" ? "dark" : "system";
    applyTheme(next);
    setThemeState(next);
  }

  const themeLabel  = theme === "system" ? t("theme.system") : theme === "dark" ? t("theme.dark") : t("theme.light");
  const hasLLM      = providers.some((p) => p.enabled && p.kind === "llm");
  const appCtx: AppContext = { hasLLMProvider: hasLLM };

  // ── Loading / auth screens ───────────────────────────────────────────────────

  if (loading) {
    return (
      <main className="auth-screen">
        <section className="panel auth-panel" aria-busy="true">
          <p className="eyebrow">Omni-AI</p>
          <h1>{t("auth.workspaceLoading")}</h1>
          <div className="auth-loading-bar" aria-hidden="true" />
        </section>
      </main>
    );
  }

  if (!principal) {
    return (
      <ToastProvider>
        <LoginScreen
          error={authError}
          t={t}
          onLogin={async (email, password) => {
            setAuthError("");
            try {
              const result = await api.login(email, password);
              setPrincipal(result.principal);
            } catch (error) {
              setAuthError(error instanceof ApiError ? error.message : t("auth.loginFailed"));
            }
          }}
        />
      </ToastProvider>
    );
  }

  // ── Nav items ────────────────────────────────────────────────────────────────

  const navItems = [
    { to: "/",          label: t("nav.overview"),  group: "main",     icon: "⊞" },
    { to: "/knowledge", label: t("nav.knowledge"), group: "main",     icon: "📂" },
    { to: "/chat",      label: t("nav.chat"),       group: "main",     icon: "💬" },
    { to: "/agents",    label: t("nav.agents"),     group: "advanced", icon: "⚡" },
    { to: "/search",    label: t("nav.search"),     group: "advanced", icon: "🔍" },
    { to: "/deploy",    label: t("nav.deploy"),     group: "advanced", icon: "🚀" },
    { to: "/admin",     label: t("nav.admin"),      group: "advanced", icon: "⚙" },
  ];

  // ── Render ───────────────────────────────────────────────────────────────────

  return (
    <ToastProvider>
      {/* WCAG 2.4.1 — Skip to main content */}
      <a href="#main-content" className="skip-link">Skip to main content</a>

      {/* Mobile overlay — closes sidebar when tapping outside */}
      {sidebarOpen && (
        <div
          className="sidebar-overlay"
          aria-hidden="true"
          onClick={() => setSidebarOpen(false)}
        />
      )}

      {/* Mobile top bar */}
      <header className="mobile-topbar" aria-label="Mobile navigation">
        <button
          type="button"
          className="hamburger"
          aria-label={sidebarOpen ? "Close menu" : "Open menu"}
          aria-expanded={sidebarOpen}
          aria-controls="sidebar"
          onClick={() => setSidebarOpen((v) => !v)}
        >
          <span />
          <span />
          <span />
        </button>
        <span className="mobile-brand">Omni-AI</span>
        <button
          type="button"
          className="theme-toggle mobile-theme-btn"
          onClick={cycleTheme}
          aria-label={`Theme: ${theme}`}
          title={t("theme.toggle")}
        >
          {themeLabel}
        </button>
      </header>

      <div className="app-shell">
        <aside
          id="sidebar"
          className={`sidebar${sidebarOpen ? " sidebar-open" : ""}`}
          aria-label="Primary navigation"
        >
          {/* Brand */}
          <div className="sidebar-brand">
            <p className="eyebrow" aria-hidden="true">Omni-AI</p>
            <h1 className="sidebar-title">Omni-AI</h1>
            <p className="muted sidebar-tenant">{principal.tenantName}</p>
          </div>

          {/* Provider health indicator */}
          {!hasLLM && providers.length > 0 /* loaded but none enabled */ && (
            <div className="sidebar-alert" role="status">
              <strong>No LLM enabled</strong>
              <NavLink to="/admin" className="sidebar-alert-link">Set up in Admin →</NavLink>
            </div>
          )}
          {providers.length === 0 && (
            <div className="sidebar-alert sidebar-alert-warn" role="status">
              <strong>Setup required</strong>
              <span>Add an AI provider to enable Chat and Agents.</span>
              <NavLink to="/admin" className="sidebar-alert-link">Open Admin →</NavLink>
            </div>
          )}

          {/* Nav */}
          <nav className="nav-list" aria-label="Primary">
            <div className="nav-group">
              <span className="nav-group-label">Start here</span>
              {navItems.filter((item) => item.group === "main").map((item) => (
                <NavLink
                  key={item.to}
                  to={item.to}
                  end={item.to === "/"}
                  className={({ isActive }) => (isActive ? "nav-link active" : "nav-link")}
                >
                  {({ isActive }) => (
                    <>
                      {isActive && <span className="sr-only">(current page)</span>}
                      <span className="nav-icon" aria-hidden="true">{item.icon}</span>
                      {item.label}
                    </>
                  )}
                </NavLink>
              ))}
            </div>
            <div className="nav-group">
              <span className="nav-group-label">Advanced</span>
              {navItems.filter((item) => item.group === "advanced").map((item) => (
                <NavLink
                  key={item.to}
                  to={item.to}
                  className={({ isActive }) => (isActive ? "nav-link active" : "nav-link")}
                >
                  {({ isActive }) => (
                    <>
                      {isActive && <span className="sr-only">(current page)</span>}
                      <span className="nav-icon" aria-hidden="true">{item.icon}</span>
                      {item.label}
                    </>
                  )}
                </NavLink>
              ))}
            </div>
          </nav>

          {/* Command palette shortcut */}
          <button
            type="button"
            className="palette-trigger"
            onClick={() => setPaletteOpen(true)}
            aria-label="Open command palette"
            aria-keyshortcuts="Control+K Meta+K"
          >
            <span>Command palette</span>
            <kbd>⌘K</kbd>
          </button>

          {/* User card */}
          <div className="user-card" role="complementary" aria-label="User account">
            <div className="user-card-info">
              <strong aria-label={`Signed in as ${principal.displayName}`}>{principal.displayName}</strong>
              <span className="user-email">{principal.email}</span>
              <span className="user-role">{principal.role}</span>
            </div>
            <div className="user-card-actions">
              <button
                type="button"
                className="theme-toggle"
                onClick={cycleTheme}
                aria-label={`${t("theme.toggle")} (currently ${theme})`}
                title={t("theme.toggle")}
              >
                {themeLabel}
              </button>
              <select
                className="lang-picker"
                value={locale}
                onChange={(e) => setLocale(e.target.value as "en" | "es")}
                aria-label="Select language"
              >
                <option value="en">EN</option>
                <option value="es">ES</option>
              </select>
            </div>
            <button
              className="secondary-button small-button signout-btn"
              type="button"
              onClick={async () => { await api.logout(); setPrincipal(null); }}
            >
              {t("auth.signOut")}
            </button>
          </div>
        </aside>

        <main id="main-content" className="content" tabIndex={-1}>
          <ErrorBoundary key={location.pathname}>
            <Routes>
              <Route path="/"          element={<HomePage appCtx={appCtx} />} />
              <Route path="/knowledge" element={<KnowledgePage />} />
              <Route path="/chat"      element={<ChatPage appCtx={appCtx} />} />
              <Route path="/agents"    element={<AgentsPage appCtx={appCtx} />} />
              <Route path="/search"    element={<SearchPage />} />
              <Route path="/deploy"    element={<DeploymentsPage />} />
              <Route path="/admin"     element={<AdminPage onProvidersChange={setProviders} />} />
              <Route
                path="*"
                element={
                  <section className="page">
                    <div className="panel stack">
                      <p className="eyebrow">Not found</p>
                      <h2>Page not found</h2>
                      <p className="empty-state">Use the sidebar to return to a workspace page.</p>
                    </div>
                  </section>
                }
              />
            </Routes>
          </ErrorBoundary>
        </main>
      </div>

      <CommandPalette open={paletteOpen} onClose={() => setPaletteOpen(false)} />
    </ToastProvider>
  );
}

// ── Login screen ──────────────────────────────────────────────────────────────

function LoginScreen({
  error,
  t,
  onLogin,
}: {
  error: string;
  t: (key: string) => string;
  onLogin: (email: string, password: string) => Promise<void>;
}) {
  const [email, setEmail]         = useState("admin@omniai.local");
  const [password, setPassword]   = useState("Admin12345!");
  const [submitting, setSubmitting] = useState(false);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSubmitting(true);
    try   { await onLogin(email, password); }
    finally { setSubmitting(false); }
  }

  return (
    <main className="auth-screen">
      <form className="panel auth-panel" onSubmit={submit} noValidate>
        <p className="eyebrow">Omni-AI Workspace</p>
        <h1>{t("auth.signIn")}</h1>
        <label>
          {t("auth.email")}
          <input
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            type="email"
            required
            autoComplete="email"
            aria-required="true"
          />
        </label>
        <label>
          {t("auth.password")}
          <input
            autoComplete="current-password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            type="password"
            required
            aria-required="true"
          />
        </label>
        {error ? <p className="alert" role="alert">{error}</p> : null}
        <button
          className="primary-button"
          type="submit"
          disabled={submitting}
          aria-busy={submitting}
        >
          {submitting ? t("auth.signingIn") : t("auth.signIn")}
        </button>
        <p className="login-hint muted">
          Default: <code>admin@omniai.local</code> / <code>Admin12345!</code>
        </p>
      </form>
    </main>
  );
}
