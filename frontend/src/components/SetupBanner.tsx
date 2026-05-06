/**
 * SetupBanner — shows a dismissible callout when the workspace needs configuration.
 *
 * Usage:
 *   <SetupBanner
 *     title="No AI provider configured"
 *     description="Chat won't work until you add an LLM provider."
 *     action={{ label: "Go to Admin →", href: "/admin" }}
 *   />
 */
import { useState } from "react";
import { Link } from "react-router-dom";

interface SetupBannerProps {
  title: string;
  description: string;
  kind?: "warning" | "info" | "error";
  action?: { label: string; href: string };
  dismissKey?: string; // localStorage key — if set, user can dismiss permanently
}

export function SetupBanner({
  title,
  description,
  kind = "warning",
  action,
  dismissKey,
}: SetupBannerProps) {
  const storageKey = dismissKey ? `omniai_banner_${dismissKey}` : null;
  const [dismissed, setDismissed] = useState(
    storageKey ? localStorage.getItem(storageKey) === "1" : false
  );

  if (dismissed) return null;

  function dismiss() {
    if (storageKey) localStorage.setItem(storageKey, "1");
    setDismissed(true);
  }

  return (
    <div className={`setup-banner setup-banner-${kind}`} role="status">
      <div className="setup-banner-icon">{kind === "warning" ? "⚠" : kind === "error" ? "✕" : "ℹ"}</div>
      <div className="setup-banner-body">
        <strong>{title}</strong>
        <span>{description}</span>
        {action && (
          <Link className="setup-banner-link" to={action.href}>
            {action.label}
          </Link>
        )}
      </div>
      <button
        type="button"
        className="setup-banner-close"
        onClick={dismiss}
        aria-label="Dismiss"
      >
        ×
      </button>
    </div>
  );
}
