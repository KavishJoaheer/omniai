import { FormEvent, useEffect, useState } from "react";
import { NavLink, Route, Routes, useNavigate } from "react-router-dom";

import { HomePage } from "../features/home/HomePage";
import { KnowledgePage } from "../features/knowledge/KnowledgePage";
import { ChatPage } from "../features/chat/ChatPage";
import { AgentsPage } from "../features/agents/AgentsPage";
import { SearchPage } from "../features/search/SearchPage";
import { AdminPage } from "../features/admin/AdminPage";
import { DeploymentsPage } from "../features/deployments/DeploymentsPage";
import { ApiError, Principal, api } from "../api/client";
import { CommandPalette } from "../components/CommandPalette";
import { useI18n, setI18nStore } from "../i18n";

// ── Theme persistence ────────────────────────────────────────────────────────

type Theme = "light" | "dark" | "system";

function getStoredTheme(): Theme {
  const v = localStorage.getItem("omniai_theme");
  if (v === "light" || v === "dark" || v === "system") return v;
  return "system";
}

function applyTheme(theme: Theme) {
  const root = document.documentElement;
  if (theme === "dark") {
    root.setAttribute("data-theme", "dark");
  } else if (theme === "light") {
    root.setAttribute("data-theme", "light");
  } else {
    root.removeAttribute("data-theme");
  }
  localStorage.setItem("omniai_theme", theme);
}

// Apply theme before first render to prevent flash
applyTheme(getStoredTheme());

// ── App ──────────────────────────────────────────────────────────────────────

export function App() {
  const { t, locale, setLocale } = useI18n();
  const [principal, setPrincipal] = useState<Principal | null>(null);
  const [loading, setLoading] = useState(true);
  const [authError, setAuthError] = useState("");
  const [theme, setThemeState] = useState<Theme>(getStoredTheme);
  const [paletteOpen, setPaletteOpen] = useState(false);

  // Publish i18n store for non-hook consumers
  useEffect(() => {
    setI18nStore({ t, locale });
  }, [t, locale]);

  useEffect(() => {
    api
      .me()
      .then(setPrincipal)
      .catch(() => setPrincipal(null))
      .finally(() => setLoading(false));
  }, []);

  // Global ⌘+K / Ctrl+K handler
  useEffect(() => {
    function onKeyDown(e: KeyboardEvent) {
      if ((e.metaKey || e.ctrlKey) && e.key === "k") {
        e.preventDefault();
        setPaletteOpen((v) => !v);
      }
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, []);

  function cycleTheme() {
    const next: Theme = theme === "system" ? "light" : theme === "light" ? "dark" : "system";
    applyTheme(next);
    setThemeState(next);
  }

  const themeIcon = theme === "dark" ? "🌙" : theme === "light" ? "☀️" : "💻";

  if (loading) {
    return (
      <main className="auth-screen">
        <section className="panel auth-panel" aria-busy="true">
          <p className="eyebrow">Omni-AI</p>
          <h1>{t("auth.workspaceLoading")}</h1>
        </section>
      </main>
    );
  }

  if (!principal) {
    return (
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
    );
  }

  const navItems = [
    { to: "/",          label: t("nav.overview") },
    { to: "/knowledge", label: t("nav.knowledge") },
    { to: "/chat",      label: t("nav.chat") },
    { to: "/agents",    label: t("nav.agents") },
    { to: "/search",    label: t("nav.search") },
    { to: "/deploy",    label: t("nav.deploy") },
    { to: "/admin",     label: t("nav.admin") },
  ];

  return (
    <>
      {/* WCAG 2.4.1 — Skip to main content */}
      <a href="#main-content" className="skip-link">
        Skip to main content
      </a>

      <div className="app-shell">
        <aside className="sidebar" aria-label="Primary navigation">
          <div>
            <p className="eyebrow" aria-hidden="true">Omni-AI</p>
            <h1 style={{ fontSize: "1.15rem", margin: "0 0 4px" }}>Omni-AI</h1>
            <p className="muted" style={{ margin: 0, fontSize: "0.83rem" }}>{principal.tenantName}</p>
          </div>

          <nav className="nav-list" aria-label="Primary">
            {navItems.map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                end={item.to === "/"}
                className={({ isActive }) => (isActive ? "nav-link active" : "nav-link")}
                aria-current={undefined}
              >
                {item.label}
              </NavLink>
            ))}
          </nav>

          {/* Keyboard shortcut hint */}
          <button
            type="button"
            className="secondary-button small-button"
            style={{ textAlign: "left", display: "flex", alignItems: "center", gap: 6, color: "#b7c2d2", background: "transparent", border: "1px solid rgba(255,255,255,0.12)" }}
            onClick={() => setPaletteOpen(true)}
            aria-label="Open command palette"
            aria-keyshortcuts="Control+K Meta+K"
          >
            <span aria-hidden="true">⌘</span>
            <span style={{ fontSize: "0.8rem" }}>Command palette</span>
            <kbd style={{ marginLeft: "auto", fontSize: "0.7rem", opacity: 0.7 }}>⌘K</kbd>
          </button>

          <div className="user-card" role="complementary" aria-label="User account">
            <strong aria-label={`Signed in as ${principal.displayName}`}>{principal.displayName}</strong>
            <span style={{ fontSize: "0.82rem" }}>{principal.email}</span>
            <span style={{ fontSize: "0.82rem" }}>{principal.role}</span>

            <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
              {/* Theme toggle */}
              <button
                type="button"
                className="theme-toggle"
                onClick={cycleTheme}
                aria-label={`${t("theme.toggle")} (currently ${theme})`}
                title={t("theme.toggle")}
              >
                <span aria-hidden="true">{themeIcon}</span>
                <span>{theme === "system" ? t("theme.system") : theme === "dark" ? t("theme.dark") : t("theme.light")}</span>
              </button>

              {/* Language picker */}
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
              className="secondary-button small-button"
              style={{ background: "transparent", border: "1px solid rgba(255,255,255,0.15)", color: "#dbe4f0" }}
              type="button"
              onClick={async () => {
                await api.logout();
                setPrincipal(null);
              }}
            >
              {t("auth.signOut")}
            </button>
          </div>
        </aside>

        <main id="main-content" className="content" tabIndex={-1}>
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

      {/* Command palette — rendered outside app-shell so it can be full-screen */}
      <CommandPalette
        open={paletteOpen}
        onClose={() => setPaletteOpen(false)}
      />
    </>
  );
}

function LoginScreen({
  error,
  t,
  onLogin,
}: {
  error: string;
  t: (key: string) => string;
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
        <button className="primary-button" type="submit" disabled={submitting} aria-busy={submitting}>
          {submitting ? t("auth.signingIn") : t("auth.signIn")}
        </button>
      </form>
    </main>
  );
}
