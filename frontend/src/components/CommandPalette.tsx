/**
 * M18 — Command Palette (⌘+K / Ctrl+K)
 *
 * Keyboard-accessible command palette that lets users jump to any page or
 * trigger common actions without touching the mouse.
 *
 * WCAG 2.1 AA compliance:
 *   - role="dialog" + aria-modal + aria-label
 *   - Focus trapped inside the dialog while open
 *   - Escape closes; Enter activates selected item
 *   - Arrow-key navigation with aria-activedescendant
 */
import { KeyboardEvent, useCallback, useEffect, useId, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";

export type PaletteCommand = {
  id: string;
  label: string;
  category?: string;
  icon?: string;
  action: () => void;
};

type Props = {
  open: boolean;
  onClose: () => void;
  extraCommands?: PaletteCommand[];
};

function useDefaultCommands(): PaletteCommand[] {
  const navigate = useNavigate();
  return [
    { id: "nav-overview",   label: "Go to Overview",   category: "Navigate", icon: "🏠", action: () => navigate("/") },
    { id: "nav-knowledge",  label: "Go to Knowledge",  category: "Navigate", icon: "📚", action: () => navigate("/knowledge") },
    { id: "nav-chat",       label: "Go to Chat",       category: "Navigate", icon: "💬", action: () => navigate("/chat") },
    { id: "nav-agents",     label: "Go to Agents",     category: "Navigate", icon: "🤖", action: () => navigate("/agents") },
    { id: "nav-search",     label: "Go to Search",     category: "Navigate", icon: "🔍", action: () => navigate("/search") },
    { id: "nav-deploy",     label: "Go to Deploy",     category: "Navigate", icon: "🚀", action: () => navigate("/deploy") },
    { id: "nav-admin",      label: "Go to Admin",      category: "Navigate", icon: "⚙️",  action: () => navigate("/admin") },
  ];
}

export function CommandPalette({ open, onClose, extraCommands = [] }: Props) {
  const paletteId = useId();
  const inputRef = useRef<HTMLInputElement>(null);
  const listRef = useRef<HTMLUListElement>(null);
  const [query, setQuery] = useState("");
  const [selectedIndex, setSelectedIndex] = useState(0);
  const defaultCommands = useDefaultCommands();
  const allCommands = [...defaultCommands, ...extraCommands];

  const filtered = query.trim()
    ? allCommands.filter((cmd) =>
        cmd.label.toLowerCase().includes(query.toLowerCase()) ||
        (cmd.category ?? "").toLowerCase().includes(query.toLowerCase())
      )
    : allCommands;

  // Reset state when opened
  useEffect(() => {
    if (open) {
      setQuery("");
      setSelectedIndex(0);
      // Focus input on next tick
      requestAnimationFrame(() => inputRef.current?.focus());
    }
  }, [open]);

  // Keep selectedIndex in bounds
  useEffect(() => {
    setSelectedIndex(0);
  }, [query]);

  // Trap focus inside the dialog
  useEffect(() => {
    if (!open) return;
    function handleFocusOut(e: FocusEvent) {
      const dialog = document.getElementById(paletteId);
      if (dialog && !dialog.contains(e.relatedTarget as Node | null)) {
        inputRef.current?.focus();
      }
    }
    document.addEventListener("focusout", handleFocusOut);
    return () => document.removeEventListener("focusout", handleFocusOut);
  }, [open, paletteId]);

  const activate = useCallback(
    (cmd: PaletteCommand) => {
      onClose();
      cmd.action();
    },
    [onClose]
  );

  function handleKeyDown(e: KeyboardEvent<HTMLInputElement>) {
    if (e.key === "Escape") {
      onClose();
      return;
    }
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setSelectedIndex((i) => Math.min(i + 1, filtered.length - 1));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setSelectedIndex((i) => Math.max(i - 1, 0));
    } else if (e.key === "Enter") {
      e.preventDefault();
      if (filtered[selectedIndex]) {
        activate(filtered[selectedIndex]);
      }
    }
  }

  if (!open) return null;

  return (
    <div
      className="palette-backdrop"
      role="presentation"
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div
        id={paletteId}
        role="dialog"
        aria-modal="true"
        aria-label="Command palette"
        className="palette-box"
      >
        <div className="palette-input-row">
          <span aria-hidden="true" style={{ color: "var(--muted)", fontSize: "1rem" }}>⌘</span>
          <input
            ref={inputRef}
            type="search"
            role="combobox"
            aria-autocomplete="list"
            aria-expanded={filtered.length > 0}
            aria-controls={`${paletteId}-results`}
            aria-activedescendant={
              filtered[selectedIndex] ? `${paletteId}-item-${selectedIndex}` : undefined
            }
            placeholder="Search commands and pages…"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={handleKeyDown}
            autoComplete="off"
            spellCheck={false}
          />
          <button
            type="button"
            onClick={onClose}
            style={{ background: "none", border: "none", cursor: "pointer", color: "var(--muted)", padding: "4px" }}
            aria-label="Close command palette"
          >
            ✕
          </button>
        </div>

        <ul
          ref={listRef}
          id={`${paletteId}-results`}
          role="listbox"
          className="palette-results"
          aria-label="Commands"
          style={{ listStyle: "none", margin: 0, padding: 0 }}
        >
          {filtered.length === 0 ? (
            <li className="palette-empty" role="option" aria-selected={false}>
              No results{query ? ` for "${query}"` : ""}
            </li>
          ) : (
            filtered.map((cmd, index) => (
              <li key={cmd.id} role="option" aria-selected={index === selectedIndex}>
                <button
                  id={`${paletteId}-item-${index}`}
                  type="button"
                  className="palette-item"
                  aria-selected={index === selectedIndex}
                  onClick={() => activate(cmd)}
                  onMouseEnter={() => setSelectedIndex(index)}
                >
                  {cmd.icon ? (
                    <span className="palette-item-icon" aria-hidden="true">{cmd.icon}</span>
                  ) : null}
                  <span className="palette-item-label">{cmd.label}</span>
                  {cmd.category ? (
                    <span className="palette-item-category">{cmd.category}</span>
                  ) : null}
                </button>
              </li>
            ))
          )}
        </ul>
      </div>
    </div>
  );
}
