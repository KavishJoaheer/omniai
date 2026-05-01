/** English (default) translations — M18 i18n */
export const en = {
  translation: {
    // Navigation
    nav: {
      overview: "Overview",
      knowledge: "Knowledge",
      chat: "Chat",
      agents: "Agents",
      search: "Search",
      deploy: "Deploy",
      admin: "Admin",
    },
    // Auth
    auth: {
      signIn: "Sign in",
      signOut: "Sign out",
      signingIn: "Signing in…",
      email: "Email",
      password: "Password",
      loginFailed: "Login failed.",
      workspaceLoading: "Loading workspace",
    },
    // Knowledge / Documents
    knowledge: {
      title: "Knowledge Base",
      collections: "Collections",
      documents: "Documents",
      upload: "Upload",
      uploading: "Uploading…",
      reindex: "Re-index",
      delete: "Delete",
      addTag: "Add tag",
      bulkDelete: "Delete selected",
      bulkReindex: "Re-index selected",
      bulkSetTags: "Set tags",
      selectedCount: "{{count}} selected",
      noDocuments: "No documents yet.",
      noCollections: "No collections yet.",
      confirmDelete: "Delete {{count}} document(s)?",
    },
    // Chat
    chat: {
      title: "Chat",
      newConversation: "New conversation",
      sendMessage: "Send",
      placeholder: "Ask a question…",
      exporting: "Exporting…",
      exportJson: "Export JSON",
      exportMarkdown: "Export Markdown",
      noConversations: "No conversations yet.",
    },
    // Agents
    agents: {
      title: "Agents",
      run: "Run",
      running: "Running…",
      exportRun: "Export run",
      noRuns: "No runs yet.",
    },
    // Command palette
    palette: {
      placeholder: "Search commands and pages…",
      noResults: "No results for "{{query}}"",
      goTo: "Go to",
      actions: "Actions",
    },
    // Theme
    theme: {
      light: "Light",
      dark: "Dark",
      system: "System",
      toggle: "Toggle theme",
    },
    // Common
    common: {
      save: "Save",
      cancel: "Cancel",
      confirm: "Confirm",
      loading: "Loading…",
      error: "Something went wrong.",
      success: "Done!",
      close: "Close",
      search: "Search",
      filter: "Filter",
      refresh: "Refresh",
      create: "Create",
      edit: "Edit",
      view: "View",
      back: "Back",
    },
  },
} as const;
