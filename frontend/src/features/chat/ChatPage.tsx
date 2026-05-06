import { FormEvent, useEffect, useMemo, useState } from "react";

import { Citation, Collection, Conversation, Document, Message, api } from "../../api/client";
import { AppContext } from "../../app/App";
import { downloadBlob } from "../../components/downloadBlob";
import { SetupBanner } from "../../components/SetupBanner";
import { HelpTip } from "../../components/Tooltip";

type LocalMessage = Pick<Message, "role" | "content" | "citations"> & { id: string };

export function ChatPage({ appCtx }: { appCtx: AppContext }) {
  const [collections, setCollections] = useState<Collection[]>([]);
  const [documents, setDocuments] = useState<Document[]>([]);
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [conversationId, setConversationId] = useState("");
  const [editingConversationId, setEditingConversationId] = useState("");
  const [editingTitle, setEditingTitle] = useState("");
  const [messages, setMessages] = useState<LocalMessage[]>([]);
  const [selectedCollections, setSelectedCollections] = useState<string[]>([]);
  const [selectedDocuments, setSelectedDocuments] = useState<string[]>([]);
  const [input, setInput] = useState("");
  const [citations, setCitations] = useState<Citation[]>([]);
  const [graphLines, setGraphLines] = useState<string[]>([]);
  const [rerank, setRerank] = useState(true);
  const [streaming, setStreaming] = useState(false);
  const [error, setError] = useState("");

  const activeConversation = useMemo(
    () => conversations.find((conversation) => conversation.id === conversationId) || null,
    [conversations, conversationId]
  );
  const sortedConversations = useMemo(() => sortConversations(conversations), [conversations]);
  const latestAssistant = useMemo(
    () => [...messages].reverse().find((message) => message.role === "assistant"),
    [messages]
  );

  useEffect(() => {
    refreshInitial();
  }, []);

  useEffect(() => {
    if (!conversationId) {
      setMessages([]);
      return;
    }
    api
      .listMessages(conversationId)
      .then((result) => {
        setMessages(result);
        const lastAssistant = [...result].reverse().find((message) => message.role === "assistant");
        setCitations(lastAssistant?.citations || []);
        setGraphLines([]);
      })
      .catch((caught) => setError(toMessage(caught)));
  }, [conversationId]);

  useEffect(() => {
    if (activeConversation) {
      setSelectedCollections(activeConversation.collection_ids);
      setSelectedDocuments([]);
    }
  }, [activeConversation]);

  useEffect(() => {
    let cancelled = false;
    async function loadDocuments() {
      if (selectedCollections.length === 0) {
        setDocuments([]);
        setSelectedDocuments([]);
        return;
      }
      const results = await Promise.allSettled(selectedCollections.map((id) => api.listDocuments(id)));
      if (cancelled) return;
      const nextDocuments = results.flatMap((result) => (result.status === "fulfilled" ? result.value : []));
      setDocuments(nextDocuments);
      setSelectedDocuments((current) => current.filter((id) => nextDocuments.some((document) => document.id === id)));
    }
    loadDocuments().catch((caught) => setError(toMessage(caught)));
    return () => {
      cancelled = true;
    };
  }, [selectedCollections]);

  async function refreshInitial() {
    setError("");
    try {
      const [collectionResult, conversationResult] = await Promise.all([
        api.listCollections(),
        api.listConversations()
      ]);
      setCollections(collectionResult);
      setSelectedCollections(collectionResult.map((collection) => collection.id));
      setConversations(sortConversations(conversationResult));
      setConversationId(sortConversations(conversationResult)[0]?.id || "");
    } catch (caught) {
      setError(toMessage(caught));
    }
  }

  async function refreshConversations(nextConversationId = conversationId) {
    const refreshed = sortConversations(await api.listConversations());
    setConversations(refreshed);
    if (nextConversationId) {
      setConversationId(nextConversationId);
    }
  }

  async function newConversation() {
    setError("");
    try {
      const created = await api.createConversation({
        title: "New conversation",
        collection_ids: selectedCollections
      });
      setConversations((current) => sortConversations([created, ...current]));
      setConversationId(created.id);
      setMessages([]);
      setCitations([]);
      setGraphLines([]);
    } catch (caught) {
      setError(toMessage(caught));
    }
  }

  async function saveConversationTitle(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!editingConversationId || !editingTitle.trim()) return;
    setError("");
    try {
      const updated = await api.updateConversation(editingConversationId, { title: editingTitle.trim() });
      setConversations((current) =>
        sortConversations(current.map((conversation) => (conversation.id === updated.id ? updated : conversation)))
      );
      setEditingConversationId("");
      setEditingTitle("");
    } catch (caught) {
      setError(toMessage(caught));
    }
  }

  async function exportConversation(id: string, fmt: "json" | "markdown") {
    setError("");
    try {
      const blob = await api.exportConversation(id, fmt);
      const ext = fmt === "json" ? "json" : "md";
      downloadBlob(blob, `conversation-${id.slice(0, 8)}.${ext}`);
    } catch (caught) {
      setError(toMessage(caught));
    }
  }

  async function togglePin(conversation: Conversation) {
    setError("");
    try {
      const updated = await api.updateConversation(conversation.id, { pinned: !conversation.pinned });
      setConversations((current) =>
        sortConversations(current.map((item) => (item.id === updated.id ? updated : item)))
      );
    } catch (caught) {
      setError(toMessage(caught));
    }
  }

  async function deleteConversation(conversation: Conversation) {
    if (!window.confirm(`Delete "${conversation.title}"?`)) return;
    setError("");
    try {
      await api.deleteConversation(conversation.id);
      const remaining = conversations.filter((item) => item.id !== conversation.id);
      setConversations(sortConversations(remaining));
      if (conversation.id === conversationId) {
        const nextId = sortConversations(remaining)[0]?.id || "";
        setConversationId(nextId);
        setMessages([]);
        setCitations([]);
        setGraphLines([]);
      }
    } catch (caught) {
      setError(toMessage(caught));
    }
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!input.trim() || streaming) return;
    const userText = input.trim();
    const assistantId = `local-${Date.now()}`;
    setInput("");
    setStreaming(true);
    setError("");
    setCitations([]);
    setGraphLines([]);
    setMessages((current) => [
      ...current,
      { id: `user-${Date.now()}`, role: "user", content: userText, citations: [] },
      { id: assistantId, role: "assistant", content: "", citations: [] }
    ]);

    try {
      await api.chat(
        {
          conversation_id: conversationId || undefined,
          message: userText,
          collection_ids: selectedCollections,
          document_ids: selectedDocuments,
          top_k: activeConversation?.collection_ids.length ? undefined : 8,
          vector_weight: 0.6,
          rerank
        },
        streamHandlers(assistantId)
      );
    } catch (caught) {
      setError(toMessage(caught));
    } finally {
      setStreaming(false);
    }
  }

  async function regenerate() {
    if (!conversationId || !latestAssistant || streaming) return;
    const assistantId = `regen-${Date.now()}`;
    setStreaming(true);
    setError("");
    setCitations([]);
    setGraphLines([]);
    setMessages((current) =>
      current.map((message) =>
        message.id === latestAssistant.id ? { ...message, id: assistantId, content: "", citations: [] } : message
      )
    );
    try {
      await api.regenerateLastMessage(conversationId, { rerank }, streamHandlers(assistantId));
    } catch (caught) {
      setError(toMessage(caught));
    } finally {
      setStreaming(false);
    }
  }

  function streamHandlers(assistantId: string) {
    return {
      onCitations: (nextCitations: Citation[], nextConversationId?: string) => {
        setCitations(nextCitations);
        if (!conversationId && nextConversationId) {
          setConversationId(nextConversationId);
        }
      },
      onGraph: (nextGraphLines: string[]) => setGraphLines(nextGraphLines),
      onDelta: (delta: string) => {
        setMessages((current) =>
          current.map((message) =>
            message.id === assistantId ? { ...message, content: `${message.content}${delta}` } : message
          )
        );
      },
      onDone: async (done: { conversation_id: string }) => {
        await refreshConversations(done.conversation_id);
        setMessages(await api.listMessages(done.conversation_id));
      },
      onError: (message: string) => setError(message)
    };
  }

  function toggleCollection(collectionId: string) {
    setSelectedCollections((current) =>
      current.includes(collectionId) ? current.filter((id) => id !== collectionId) : [...current, collectionId]
    );
  }

  function toggleDocument(documentId: string) {
    setSelectedDocuments((current) =>
      current.includes(documentId) ? current.filter((id) => id !== documentId) : [...current, documentId]
    );
  }

  return (
    <section className="page">
      {!appCtx.hasLLMProvider && (
        <SetupBanner
          title="No LLM provider configured"
          description="Go to Admin and add an AI provider (OpenAI, Anthropic, Ollama, etc.) to enable chat."
          kind="warning"
          action={{ label: "Set up in Admin →", href: "/admin" }}
        />
      )}
      <header className="page-header">
        <div>
          <p className="eyebrow">Grounded Chat</p>
          <h2>{activeConversation?.title || "RAG chat"}</h2>
        </div>
        <div className="button-row">
          {conversationId && (
            <>
              <button
                className="secondary-button small-button"
                type="button"
                onClick={() => exportConversation(conversationId, "markdown")}
                title="Export as Markdown"
              >
                ↓ MD
              </button>
              <button
                className="secondary-button small-button"
                type="button"
                onClick={() => exportConversation(conversationId, "json")}
                title="Export as JSON"
              >
                ↓ JSON
              </button>
            </>
          )}
          <button className="secondary-button" type="button" onClick={regenerate} disabled={!latestAssistant || streaming}>
            Regenerate
          </button>
          <button className="primary-button" type="button" onClick={newConversation}>
            New chat
          </button>
        </div>
      </header>

      {error ? <p className="alert">{error}</p> : null}

      <div className="chat-layout">
        <aside className="panel side-panel stack">
          <div className="section-heading">
            <h3>Conversations</h3>
            <button className="secondary-button small-button" type="button" onClick={refreshInitial}>
              Refresh
            </button>
          </div>
          <div className="list-box">
            {sortedConversations.map((conversation) => (
              <div
                className={conversation.id === conversationId ? "list-row selected" : "list-row"}
                key={conversation.id}
              >
                {editingConversationId === conversation.id ? (
                  <form className="inline-form" onSubmit={saveConversationTitle}>
                    <input value={editingTitle} onChange={(event) => setEditingTitle(event.target.value)} />
                    <button className="primary-button small-button" type="submit">
                      Save
                    </button>
                  </form>
                ) : (
                  <>
                    <button className="plain-button" onClick={() => setConversationId(conversation.id)} type="button">
                      <strong>{conversation.pinned ? "Pinned " : ""}{conversation.title}</strong>
                      <small>{conversation.collection_ids.length} collections</small>
                    </button>
                    <div className="button-row">
                      <button className="secondary-button small-button" type="button" onClick={() => togglePin(conversation)}>
                        {conversation.pinned ? "Unpin" : "Pin"}
                      </button>
                      <button
                        className="secondary-button small-button"
                        type="button"
                        onClick={() => {
                          setEditingConversationId(conversation.id);
                          setEditingTitle(conversation.title);
                        }}
                      >
                        Rename
                      </button>
                      <button
                        className="secondary-button small-button"
                        type="button"
                        onClick={() => exportConversation(conversation.id, "markdown")}
                        title="Export as Markdown"
                      >
                        Export
                      </button>
                      <button className="danger-button small-button" type="button" onClick={() => deleteConversation(conversation)}>
                        Delete
                      </button>
                    </div>
                  </>
                )}
              </div>
            ))}
            {sortedConversations.length === 0 ? <p className="empty-state">No conversations yet.</p> : null}
          </div>
        </aside>

        <article className="panel conversation-panel">
          <div className="stack filter-bar">
            <div className="section-heading">
              <div>
                <h3>Context filters</h3>
                <p>Choose collections and optional documents before sending.</p>
              </div>
              <label className="inline-check">
                <input checked={rerank} onChange={(event) => setRerank(event.target.checked)} type="checkbox" />
                Rerank <HelpTip text="Re-orders retrieved passages by relevance before answering. Gives better results but is slightly slower." />
              </label>
            </div>
            <div className="collection-filter">
              {collections.map((collection) => (
                <label className="check-row" key={collection.id}>
                  <input
                    checked={selectedCollections.includes(collection.id)}
                    onChange={() => toggleCollection(collection.id)}
                    type="checkbox"
                  />
                  <span>{collection.name}</span>
                </label>
              ))}
            </div>
            <div className="collection-filter">
              {documents.map((document) => (
                <label className="check-row" key={document.id}>
                  <input
                    checked={selectedDocuments.includes(document.id)}
                    onChange={() => toggleDocument(document.id)}
                    type="checkbox"
                  />
                  <span>
                    <strong>{document.name}</strong>
                    <small>{document.status}</small>
                  </span>
                </label>
              ))}
              {documents.length === 0 ? <p className="empty-state">Select a collection to filter by document.</p> : null}
            </div>
          </div>

          <div className="conversation-scroll">
            {messages.map((message) => (
              <div className={`message ${message.role === "user" ? "user" : "assistant"}`} key={message.id}>
                <span className="message-role">{message.role}</span>
                <p>{message.content || (streaming && message.role === "assistant" ? "Thinking..." : "")}</p>
              </div>
            ))}
            {messages.length === 0 ? <p className="empty-state">Start a cited conversation.</p> : null}
          </div>
          <form className="composer" onSubmit={submit}>
            <textarea
              value={input}
              onChange={(event) => setInput(event.target.value)}
              placeholder="Ask across the selected knowledge"
              rows={3}
            />
            <button className="primary-button" type="submit" disabled={streaming || !input.trim()}>
              Send
            </button>
          </form>
        </article>

        <aside className="panel side-panel stack">
          <h3>Citations</h3>
          <div className="citation-list">
            {citations.map((citation) => (
              <button
                className="citation-card citation-button"
                key={`${citation.index}-${citation.chunk_id}`}
                onClick={() => window.open(`/v1/documents/${citation.document_id}/raw`, "_blank")}
                type="button"
              >
                <strong>[{citation.index}] {citation.document_name}</strong>
                <p>{citation.snippet}</p>
                <small>{citation.score.toFixed(3)}</small>
              </button>
            ))}
            {citations.length === 0 ? <p className="empty-state">Citations arrive before streamed text.</p> : null}
          </div>

          <h3>Knowledge Graph</h3>
          <div className="graph-context">
            {graphLines.map((line) => (
              <small key={line}>{line}</small>
            ))}
            {graphLines.length === 0 ? <p className="empty-state">Graph context appears when retrieval finds triples.</p> : null}
          </div>
        </aside>
      </div>
    </section>
  );
}

function sortConversations(conversations: Conversation[]) {
  return [...conversations].sort((a, b) => {
    if (a.pinned !== b.pinned) return a.pinned ? -1 : 1;
    return new Date(b.updated_at).getTime() - new Date(a.updated_at).getTime();
  });
}

function toMessage(error: unknown) {
  return error instanceof Error ? error.message : "Request failed.";
}
