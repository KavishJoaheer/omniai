import { useEffect, useState } from "react";
import { Link } from "react-router-dom";

import { Agent, Collection, Conversation, api } from "../../api/client";
import { AppContext } from "../../app/App";
import { Skeleton, SkeletonCard } from "../../components/Skeleton";
import { SetupBanner } from "../../components/SetupBanner";

interface HomePageProps {
  appCtx: AppContext;
}

export function HomePage({ appCtx }: HomePageProps) {
  const [health, setHealth]             = useState<string | null>(null);
  const [collections, setCollections]   = useState<Collection[] | null>(null);
  const [agents, setAgents]             = useState<Agent[] | null>(null);
  const [conversations, setConversations] = useState<Conversation[] | null>(null);

  const loading = health === null || collections === null;

  useEffect(() => {
    api.health().then((r) => setHealth(r.status)).catch(() => setHealth("offline"));
    api.listCollections().then(setCollections).catch(() => setCollections([]));
    api.listAgents().then(setAgents).catch(() => setAgents([]));
    api.listConversations().then(setConversations).catch(() => setConversations([]));
  }, []);

  const ready         = health === "healthy" || health === "ok";
  const docCount      = (collections ?? []).reduce((n, c) => n + c.document_count, 0);
  const hasCollections = (collections?.length ?? 0) > 0;
  const hasDocuments  = docCount > 0;

  // Checklist: which setup steps are done?
  const steps = [
    {
      done: appCtx.hasLLMProvider,
      label: "Add an AI provider (OpenAI, Anthropic, Ollama…)",
      href: "/admin",
      hint: "Chat and Agents won't work without one.",
    },
    {
      done: hasCollections,
      label: "Create a Collection to organise your documents",
      href: "/knowledge",
      hint: "A collection is like a folder — group related files together.",
    },
    {
      done: hasDocuments,
      label: "Upload at least one document",
      href: "/knowledge",
      hint: "PDF, Word, HTML, or plain text — up to 100 MB each.",
    },
    {
      done: (conversations?.length ?? 0) > 0,
      label: "Ask your first question in Chat",
      href: "/chat",
      hint: "The AI will answer using your uploaded documents with citations.",
    },
  ];
  const doneCount = steps.filter((s) => s.done).length;
  const allDone   = doneCount === steps.length;

  return (
    <section className="page">
      {/* Provider warning — only when providers confirmed loaded but none available */}
      {!appCtx.hasLLMProvider && (
        <SetupBanner
          title="No AI provider configured"
          description="You need to add an LLM provider before Chat or Agents will work."
          kind="warning"
          action={{ label: "Set up in Admin →", href: "/admin" }}
          dismissKey="no-provider"
        />
      )}

      <header className="welcome-header">
        <div>
          <p className="eyebrow">Home</p>
          <h2>Ask questions from your documents</h2>
          <p>
            Upload your files, then chat with them. Omni-AI finds the relevant
            passages and cites them in every answer.
          </p>
        </div>
        <Link
          className="primary-button welcome-action"
          to={hasDocuments ? "/chat" : "/knowledge"}
        >
          {hasDocuments ? "Ask a question →" : "Add documents →"}
        </Link>
      </header>

      {/* Status bar */}
      <div className="home-status-bar" aria-label="Workspace summary">
        {loading ? (
          <>
            <span><Skeleton width="80px" /></span>
            <span><Skeleton width="80px" /></span>
            <span><Skeleton width="80px" /></span>
            <span><Skeleton width="80px" /></span>
          </>
        ) : (
          <>
            <span className={`status-pill ${ready ? "ready" : ""}`}>
              {ready ? "Backend ready" : `Backend: ${health}`}
            </span>
            <span>{(collections ?? []).length} collection{(collections ?? []).length === 1 ? "" : "s"}</span>
            <span>{docCount} document{docCount === 1 ? "" : "s"}</span>
            <span>{(conversations ?? []).length} conversation{(conversations ?? []).length === 1 ? "" : "s"}</span>
          </>
        )}
      </div>

      {/* Setup checklist — only show until workspace is fully set up */}
      {!allDone && (
        <section className="panel setup-checklist" aria-label="Setup checklist">
          <div className="setup-checklist-header">
            <h3>Getting started</h3>
            <span className="setup-progress">
              {doneCount} / {steps.length} done
            </span>
          </div>
          <div className="setup-progress-bar" aria-hidden="true">
            <div
              className="setup-progress-fill"
              style={{ width: `${(doneCount / steps.length) * 100}%` }}
            />
          </div>
          <ol className="setup-steps">
            {steps.map((step, i) => (
              <li
                key={i}
                className={`setup-step ${step.done ? "setup-step-done" : ""}`}
              >
                <span className="setup-step-check" aria-hidden="true">
                  {step.done ? "✓" : i + 1}
                </span>
                <div className="setup-step-body">
                  <Link
                    to={step.href}
                    className={`setup-step-label ${step.done ? "done-label" : ""}`}
                  >
                    {step.label}
                  </Link>
                  {!step.done && (
                    <span className="setup-step-hint">{step.hint}</span>
                  )}
                </div>
              </li>
            ))}
          </ol>
        </section>
      )}

      {/* Quick metric cards */}
      <div className="summary-grid">
        {loading ? (
          <>
            <SkeletonCard />
            <SkeletonCard />
            <SkeletonCard />
            <SkeletonCard />
          </>
        ) : (
          <>
            <article className="metric-card">
              <span>Backend</span>
              <strong className={ready ? "text-success" : "text-danger"}>
                {ready ? "Healthy" : health}
              </strong>
            </article>
            <article className="metric-card">
              <span>Collections</span>
              <strong>{(collections ?? []).length}</strong>
            </article>
            <article className="metric-card">
              <span>Documents</span>
              <strong>{docCount}</strong>
            </article>
            <article className="metric-card">
              <span>Conversations</span>
              <strong>{(conversations ?? []).length}</strong>
            </article>
          </>
        )}
      </div>

      {/* Main action cards */}
      <div className="getting-started-grid">
        <Link className="panel start-card primary-start" to="/knowledge">
          <span className="step-number">1</span>
          <div>
            <p className="eyebrow">Add knowledge</p>
            <h3>Upload the files people should ask about</h3>
            <p>
              Create a collection, upload documents, and Omni-AI will parse,
              chunk, and index them automatically.
            </p>
            {!hasDocuments && (
              <span className="start-card-badge">Start here</span>
            )}
          </div>
        </Link>
        <Link className="panel start-card primary-start" to="/chat">
          <span className="step-number">2</span>
          <div>
            <p className="eyebrow">Ask</p>
            <h3>Chat with your workspace</h3>
            <p>
              Ask plain-language questions. The AI searches your documents and
              cites the exact passages behind every answer.
            </p>
            {hasDocuments && !((conversations?.length ?? 0) > 0) && (
              <span className="start-card-badge">Ready — try it now</span>
            )}
          </div>
        </Link>
        <section className="panel next-panel" aria-label="Optional tools">
          <p className="eyebrow">Optional tools</p>
          <div className="simple-link-list">
            <Link to="/search">
              <strong>Find passages</strong>
              <span>See exactly what the AI retrieves before answering.</span>
            </Link>
            <Link to="/agents">
              <strong>Automate a workflow</strong>
              <span>
                Build agents that search, run code, and ask for approval
                — then run them on a schedule.
              </span>
            </Link>
            <Link to="/deploy">
              <strong>Publish a chat page</strong>
              <span>Share a public URL so anyone can ask questions.</span>
            </Link>
            <Link to="/admin">
              <strong>Manage settings</strong>
              <span>AI providers, API keys, users, audit log.</span>
            </Link>
          </div>
        </section>
      </div>
    </section>
  );
}
