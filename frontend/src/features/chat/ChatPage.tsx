export function ChatPage() {
  return (
    <section className="page">
      <header className="page-header">
        <div>
          <p className="eyebrow">Grounded Chat</p>
          <h2>Assistant shell</h2>
        </div>
        <button className="secondary-button" type="button">
          Compare models
        </button>
      </header>
      <div className="chat-layout">
        <article className="panel conversation-panel">
          <div className="message assistant">
            <span className="message-role">Assistant</span>
            <p>
              This is the UI shell for cited, streamed answers. The backend routes are in
              place for the platform starter; retrieval and generation will plug in next.
            </p>
          </div>
          <div className="message user">
            <span className="message-role">User</span>
            <p>Show me the source citations for the policy update.</p>
          </div>
        </article>
        <aside className="panel side-panel">
          <h3>Source Drawer</h3>
          <p>Citation chips, snippets, and original document jump targets will render here.</p>
        </aside>
      </div>
    </section>
  );
}

