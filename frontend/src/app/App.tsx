import { NavLink, Route, Routes } from "react-router-dom";

import { HomePage } from "../features/home/HomePage";
import { KnowledgePage } from "../features/knowledge/KnowledgePage";
import { ChatPage } from "../features/chat/ChatPage";
import { AgentsPage } from "../features/agents/AgentsPage";
import { SearchPage } from "../features/search/SearchPage";
import { AdminPage } from "../features/admin/AdminPage";

const navItems = [
  { to: "/", label: "Overview" },
  { to: "/knowledge", label: "Knowledge" },
  { to: "/chat", label: "Chat" },
  { to: "/agents", label: "Agents" },
  { to: "/search", label: "Search" },
  { to: "/admin", label: "Admin" }
];

export function App() {
  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div>
          <p className="eyebrow">Mauritius Telecom</p>
          <h1>Omni-AI</h1>
          <p className="muted">
            Self-hostable retrieval, grounded chat, and agent workflows.
          </p>
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
      </aside>
      <main className="content">
        <Routes>
          <Route path="/" element={<HomePage />} />
          <Route path="/knowledge" element={<KnowledgePage />} />
          <Route path="/chat" element={<ChatPage />} />
          <Route path="/agents" element={<AgentsPage />} />
          <Route path="/search" element={<SearchPage />} />
          <Route path="/admin" element={<AdminPage />} />
        </Routes>
      </main>
    </div>
  );
}

