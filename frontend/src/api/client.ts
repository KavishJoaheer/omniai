export type Envelope<T> = {
  code: number;
  message: string;
  data: T;
};

export type Principal = {
  userId: string;
  email: string;
  displayName: string;
  tenantId: string;
  tenantName: string;
  role: string;
  authType?: string;
  apiKeyId?: string | null;
};

export type AuthResult = {
  accessToken: string;
  sessionTtlMinutes?: number;
  principal: Principal;
};

export type Collection = {
  id: string;
  tenant_id: string;
  name: string;
  description: string | null;
  embedding_model: string;
  chunk_template: string;
  system_prompt: string | null;
  top_k: number;
  vector_weight: number;
  document_count: number;
  created_at: string;
  updated_at: string;
};

export type Document = {
  id: string;
  tenant_id: string;
  collection_id: string;
  name: string;
  mime_type: string;
  size_bytes: number;
  status: "PENDING" | "PARSING" | "PARSED" | "EMBEDDING" | "INDEXING" | "READY" | "FAILED" | "CANCELLED";
  object_key: string | null;
  parsed_text_key: string | null;
  content_sha256: string | null;
  page_count: number;
  parser_name: string | null;
  error_message: string | null;
  parsed_at: string | null;
  tags: string[];
  created_at: string;
  updated_at: string;
};

export type DocumentStatus = {
  status: Document["status"];
  progress_pct: number;
  error_message: string | null;
  stage: string;
};

export type Chunk = {
  id: string;
  ordinal: number;
  text: string;
  char_count: number;
  token_count: number;
  template_name: string;
  metadata: Record<string, unknown>;
  parent_chunk_id: string | null;
  is_indexable: boolean;
  indexed_at: string | null;
};

export type RetrievalHit = {
  chunk_id: string;
  document_id: string;
  collection_id: string;
  score: number;
  text: string;
  snippet: string;
  metadata: {
    document_name?: string;
    filename?: string;
    graph_context?: string[];
    first_stage_score?: number;
    rerank_score?: number;
    kind?: string;
    [key: string]: unknown;
  };
};

export type RetrievalResponse = {
  hits: RetrievalHit[];
  embedding_model: string;
  vector_weight: number;
};

export type Citation = {
  index: number;
  chunk_id: string;
  document_id: string;
  document_name: string;
  collection_id: string;
  score: number;
  snippet: string;
};

export type Conversation = {
  id: string;
  title: string;
  model_provider: string | null;
  model_name: string | null;
  collection_ids: string[];
  pinned: boolean;
  created_at: string;
  updated_at: string;
};

export type Message = {
  id: string;
  role: string;
  content: string;
  citations: Citation[];
  created_at: string;
};

export type GraphTriple = {
  id: string;
  collection_id: string;
  document_id: string;
  subject: string;
  predicate: string;
  object: string;
  confidence: number;
  created_at: string;
};

export type Reference = {
  index: number;
  label: string;
  chunkId: string;
  collectionId: string;
  documentId: string;
  documentName: string;
  score: number;
  snippet: string;
};

export type Agent = {
  id: string;
  tenant_id: string;
  name: string;
  description: string | null;
  definition: {
    version?: number;
    nodes?: Array<{ id: string; type: string; label?: string; config?: Record<string, unknown>; message?: string }>;
    edges?: Array<{ from: string; to: string }>;
    collectionIds?: string[];
    retrieval?: {
      topK?: number;
      vectorWeight?: number;
      similarityThreshold?: number;
    };
    generation?: {
      mode?: string;
      fallbackText?: string;
    };
    [key: string]: unknown;
  };
  published: boolean;
  created_at: string;
  updated_at: string;
};

export type AgentRun = {
  id: string;
  tenant_id: string;
  agent_id: string;
  status: "QUEUED" | "RUNNING" | "COMPLETED" | "FAILED" | "CANCELLED";
  input: { input?: string; variables?: Record<string, unknown> };
  output: { answer?: string; references?: Reference[]; usage?: Record<string, number>; error?: string };
  events: Array<{
    event: string;
    nodeId: string;
    data: Record<string, unknown>;
    createdAt: string;
  }>;
  error_message: string | null;
  started_at: string | null;
  completed_at: string | null;
  created_at: string;
  updated_at: string;
};

export type TenantInfo = {
  id: string;
  slug: string;
  name: string;
  memberCount: number;
  teamCount: number;
  role: string;
};

export type Team = {
  id: string;
  name: string;
  description: string | null;
  memberCount?: number;
  myRole?: string | null;
  createdAt: string;
};

export type UserSummary = {
  id: string;
  email: string;
  displayName: string;
  role: string;
  isActive: boolean;
  createdAt: string;
};

export type AuditEvent = {
  id: string;
  action: string;
  targetType: string;
  targetId: string;
  detail: Record<string, unknown>;
  actorUserId: string | null;
  createdAt: string;
};

export type ApiKeySummary = {
  id: string;
  name: string;
  prefix: string;
  scopes: string[];
  createdAt: string;
  lastUsedAt: string | null;
  revokedAt: string | null;
  createdByUserId?: string;
};

export type ApiKeyCreated = ApiKeySummary & {
  token: string;
};

export type Provider = {
  id: string;
  kind: string;
  name: string;
  baseUrl: string | null;
  defaultModel: string | null;
  enabled: boolean;
  hasCredentials: boolean;
  options: Record<string, unknown>;
  createdAt?: string;
  updatedAt?: string;
};

export type Deployment = {
  id: string;
  name: string;
  slug: string;
  kind: "public_chat" | "webhook";
  target_kind: "collection" | "agent";
  target_id: string;
  system_prompt_override: string | null;
  model_provider: string | null;
  model_name: string | null;
  anonymous_allowed: boolean;
  rate_limit_per_minute: number;
  daily_message_quota: number;
  branding: Record<string, unknown>;
  status: "ACTIVE" | "PAUSED" | "DELETED";
  version: number;
  message_count: number;
  today_message_count: number;
  last_message_at: string | null;
  created_at: string;
  updated_at: string;
  public_url_path: string;
};

export type Connector = {
  id: string;
  collection_id: string;
  name: string;
  kind: "local_folder" | "s3" | "web_crawler" | "google_drive" | "sharepoint" | "notion" | "confluence" | "slack" | "database";
  config: Record<string, unknown>;
  enabled: boolean;
  sync_interval_seconds: number;
  last_sync_at: string | null;
  last_error: string | null;
  last_synced_count: number;
  created_at: string;
  updated_at: string;
};

export type SandboxResult = {
  exit_code: number;
  stdout: string;
  stderr: string;
  duration_seconds: number;
  timed_out: boolean;
  artifacts: Record<string, string>;
};

export type ChatEvent =
  | { kind: "citations"; citations: Citation[]; conversation_id?: string }
  | { kind: "graph"; graph_lines: string[]; conversation_id?: string }
  | { kind: "delta"; delta: string }
  | { kind: "done"; finish_reason: string; conversation_id: string; message_id: string }
  | { kind: "error"; error: string };

export type ChatBody = {
  conversation_id?: string;
  message: string;
  collection_ids?: string[];
  document_ids?: string[];
  top_k?: number;
  vector_weight?: number;
  temperature?: number;
  model_provider?: string;
  model_name?: string;
  system_prompt?: string;
  rerank?: boolean;
};

export class ApiError extends Error {
  status: number;

  constructor(message: string, status: number) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const response = await fetch(path, {
    credentials: "include",
    headers: {
      ...(options.body instanceof FormData ? {} : { "Content-Type": "application/json" }),
      ...options.headers
    },
    ...options
  });

  if (!response.ok) {
    throw new ApiError(await responseError(response), response.status);
  }

  const body = await response.json();
  if (body && typeof body === "object" && "data" in body && "code" in body) {
    return (body as Envelope<T>).data;
  }
  return body as T;
}

async function responseError(response: Response) {
  let message = response.statusText;
  try {
    const body = await response.json();
    message = body.detail || body.message || message;
  } catch {
    // Keep the status text when the response is not JSON.
  }
  return message;
}

function graphQuery(params: { entity?: string; limit?: number; offset?: number } = {}) {
  const search = new URLSearchParams();
  if (params.entity) search.set("entity", params.entity);
  if (params.limit) search.set("limit", String(params.limit));
  if (params.offset) search.set("offset", String(params.offset));
  const text = search.toString();
  return text ? `?${text}` : "";
}

async function streamSsePost(
  path: string,
  payload: Record<string, unknown>,
  handlers: {
    onEvent?: (event: ChatEvent) => void;
    onCitations?: (citations: Citation[], conversationId?: string) => void;
    onGraph?: (graphLines: string[], conversationId?: string) => void;
    onDelta?: (delta: string) => void;
    onDone?: (event: Extract<ChatEvent, { kind: "done" }>) => void;
    onError?: (error: string) => void;
  } = {}
) {
  const response = await fetch(path, {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload)
  });

  if (!response.ok || !response.body) {
    throw new ApiError(await responseError(response), response.status);
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const events = buffer.split("\n\n");
    buffer = events.pop() || "";
    for (const event of events) {
      const dataLine = event.split("\n").find((line) => line.startsWith("data:"));
      if (!dataLine) continue;
      try {
        const data = JSON.parse(dataLine.replace("data:", "").trim()) as ChatEvent;
        handlers.onEvent?.(data);
        if (data.kind === "citations") handlers.onCitations?.(data.citations || [], data.conversation_id);
        if (data.kind === "graph") handlers.onGraph?.(data.graph_lines || [], data.conversation_id);
        if (data.kind === "delta") handlers.onDelta?.(data.delta || "");
        if (data.kind === "done") handlers.onDone?.(data);
        if (data.kind === "error") handlers.onError?.(data.error || "Chat failed.");
      } catch {
        // Ignore malformed SSE payloads and keep reading the stream.
      }
    }
  }
}

export const api = {
  me: () => request<Principal>("/v1/auth/me"),
  login: (email: string, password: string) =>
    request<AuthResult>("/v1/auth/login", {
      method: "POST",
      body: JSON.stringify({ email, password })
    }),
  logout: () => request<{ loggedOut: boolean }>("/v1/auth/logout", { method: "POST" }),

  health: () => request<{ name: string; environment: string; status: string }>("/v1/health"),

  listCollections: () => request<Collection[]>("/v1/collections"),
  createCollection: (payload: Partial<Collection> & { name: string }) =>
    request<Collection>("/v1/collections", {
      method: "POST",
      body: JSON.stringify(payload)
    }),
  updateCollection: (collectionId: string, payload: Partial<Collection>) =>
    request<Collection>(`/v1/collections/${collectionId}`, {
      method: "PATCH",
      body: JSON.stringify(payload)
    }),
  deleteCollection: (collectionId: string) =>
    request<{ deleted: string }>(`/v1/collections/${collectionId}`, { method: "DELETE" }),
  listCollectionGraph: (
    collectionId: string,
    params: { entity?: string; limit?: number; offset?: number } = {}
  ) => request<GraphTriple[]>(`/v1/collections/${collectionId}/graph${graphQuery(params)}`),

  listDocuments: (collectionId: string) => request<Document[]>(`/v1/collections/${collectionId}/documents`),
  listDocumentsByTag: (collectionId: string, tag: string) =>
    request<Document[]>(`/v1/collections/${collectionId}/documents/by-tag/${encodeURIComponent(tag)}`),
  uploadDocument: (collectionId: string, file: File) => {
    const form = new FormData();
    form.append("file", file);
    return request<Document>(`/v1/collections/${collectionId}/documents/upload`, {
      method: "POST",
      body: form
    });
  },
  bulkUploadDocuments: (collectionId: string, files: File[]) => {
    const form = new FormData();
    files.forEach((file) => form.append("files", file));
    return request<Document[]>(`/v1/collections/${collectionId}/documents/bulk-upload`, {
      method: "POST",
      body: form
    });
  },
  deleteDocument: (documentId: string) =>
    request<{ deleted: string }>(`/v1/documents/${documentId}`, { method: "DELETE" }),
  getDocumentText: (documentId: string) => request<{ text: string }>(`/v1/documents/${documentId}/text`),
  getDocumentStatus: (documentId: string) => request<DocumentStatus>(`/v1/documents/${documentId}/status`),
  reindexDocument: (documentId: string, payload: { chunk_template?: string; embedding_model?: string } = {}) =>
    request<Document>(`/v1/documents/${documentId}/reindex`, {
      method: "POST",
      body: JSON.stringify(payload)
    }),
  setDocumentTags: (documentId: string, tags: string[]) =>
    request<Document>(`/v1/documents/${documentId}/tags`, {
      method: "PUT",
      body: JSON.stringify({ tags })
    }),
  listChunks: (documentId: string) => request<Chunk[]>(`/v1/documents/${documentId}/chunks`),
  listDocumentGraph: (
    documentId: string,
    params: { entity?: string; limit?: number; offset?: number } = {}
  ) => request<GraphTriple[]>(`/v1/documents/${documentId}/graph${graphQuery(params)}`),

  retrieve: (payload: {
    query: string;
    top_k?: number;
    vector_weight?: number;
    collection_ids?: string[];
    document_ids?: string[];
    embedding_model?: string;
    rerank?: boolean;
  }) =>
    request<RetrievalResponse>("/v1/retrieve", {
      method: "POST",
      body: JSON.stringify(payload)
    }),

  listConversations: () => request<Conversation[]>("/v1/conversations"),
  createConversation: (payload: {
    title?: string;
    collection_ids?: string[];
    top_k?: number;
    vector_weight?: number;
    system_prompt?: string;
    model_provider?: string;
    model_name?: string;
    temperature?: number;
  }) =>
    request<Conversation>("/v1/conversations", {
      method: "POST",
      body: JSON.stringify(payload)
    }),
  updateConversation: (
    conversationId: string,
    payload: Partial<Pick<Conversation, "title" | "pinned" | "model_provider" | "model_name">> & {
      system_prompt?: string | null;
    }
  ) =>
    request<Conversation>(`/v1/conversations/${conversationId}`, {
      method: "PATCH",
      body: JSON.stringify(payload)
    }),
  deleteConversation: (conversationId: string) =>
    request<{ deleted: string }>(`/v1/conversations/${conversationId}`, { method: "DELETE" }),
  listMessages: (conversationId: string) => request<Message[]>(`/v1/conversations/${conversationId}/messages`),
  regenerateLastMessage: (
    conversationId: string,
    payload: { temperature?: number; model_provider?: string; model_name?: string; rerank?: boolean },
    handlers: Parameters<typeof streamSsePost>[2] = {}
  ) => streamSsePost(`/v1/conversations/${conversationId}/regenerate`, payload, handlers),
  chat: (payload: ChatBody, handlers: Parameters<typeof streamSsePost>[2] = {}) => streamSsePost("/v1/chat", payload, handlers),

  listAgents: () => request<Agent[]>("/v1/agents"),
  createAgent: (payload: {
    name: string;
    description?: string | null;
    definition?: Agent["definition"];
  }) =>
    request<Agent>("/v1/agents", {
      method: "POST",
      body: JSON.stringify(payload)
    }),
  updateAgent: (agentId: string, payload: Partial<Pick<Agent, "name" | "description" | "definition" | "published">>) =>
    request<Agent>(`/v1/agents/${agentId}`, {
      method: "PATCH",
      body: JSON.stringify(payload)
    }),
  deleteAgent: (agentId: string) =>
    request<{ id: string; deleted: boolean }>(`/v1/agents/${agentId}`, {
      method: "DELETE"
    }),
  publishAgent: (agentId: string) =>
    request<Agent>(`/v1/agents/${agentId}/publish`, {
      method: "POST"
    }),
  listAgentRuns: (agentId: string) => request<AgentRun[]>(`/v1/agents/${agentId}/runs`),
  startAgentRun: (agentId: string, input: string, variables: Record<string, unknown> = {}) =>
    request<AgentRun>(`/v1/agents/${agentId}/runs`, {
      method: "POST",
      body: JSON.stringify({ input, variables })
    }),

  tenant: () => request<TenantInfo>("/v1/tenants/current"),
  teams: () => request<Team[]>("/v1/teams"),
  users: () => request<UserSummary[]>("/v1/admin/users"),
  auditEvents: () => request<AuditEvent[]>("/v1/admin/audit-events"),
  apiKeys: () => request<ApiKeySummary[]>("/v1/api-keys"),
  createApiKey: (name: string, scopes: string[]) =>
    request<ApiKeyCreated>("/v1/api-keys", {
      method: "POST",
      body: JSON.stringify({ name, scopes })
    }),
  revokeApiKey: (id: string) =>
    request<{ id: string; revokedAt: string }>(`/v1/api-keys/${id}/revoke`, {
      method: "POST"
    }),
  providers: () => request<Provider[]>("/v1/providers"),

  // Deploy Manager
  listDeployments: () => request<Deployment[]>("/v1/deployments"),
  createDeployment: (payload: {
    name: string;
    slug?: string;
    kind: string;
    target_kind: string;
    target_id: string;
    anonymous_allowed?: boolean;
    daily_message_quota?: number;
    rate_limit_per_minute?: number;
    system_prompt_override?: string | null;
    branding?: Record<string, unknown>;
  }) =>
    request<Deployment>("/v1/deployments", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  updateDeployment: (id: string, payload: {
    name?: string;
    status?: "ACTIVE" | "PAUSED";
    anonymous_allowed?: boolean;
    daily_message_quota?: number;
    system_prompt_override?: string | null;
    branding?: Record<string, unknown>;
  }) =>
    request<Deployment>(`/v1/deployments/${id}`, {
      method: "PATCH",
      body: JSON.stringify(payload),
    }),
  deleteDeployment: (id: string) =>
    request<{ deleted: string }>(`/v1/deployments/${id}`, { method: "DELETE" }),
  getDeploymentPublicInfo: (slug: string) =>
    request<{ name: string; slug: string; anonymous_allowed: boolean; kind: string; target_kind: string; branding: Record<string, unknown> }>(
      `/c/${slug}/info`
    ),

  // Connectors
  listConnectors: (collectionId?: string) =>
    request<Connector[]>(`/v1/connectors${collectionId ? `?collection_id=${collectionId}` : ""}`),
  createConnector: (payload: {
    collection_id: string;
    name: string;
    kind: Connector["kind"];
    config: Record<string, unknown>;
    sync_interval_seconds?: number;
  }) =>
    request<Connector>("/v1/connectors", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  updateConnector: (id: string, payload: { enabled?: boolean; config?: Record<string, unknown>; sync_interval_seconds?: number }) =>
    request<Connector>(`/v1/connectors/${id}`, {
      method: "PATCH",
      body: JSON.stringify(payload),
    }),
  deleteConnector: (id: string) =>
    request<{ deleted: string }>(`/v1/connectors/${id}`, { method: "DELETE" }),
  syncConnector: (id: string) =>
    request<{ connector_id: string; discovered: number; ingested: number; skipped_duplicate: number; errors: string[] }>(
      `/v1/connectors/${id}/sync`,
      { method: "POST" }
    ),

  // Sandbox
  runSandbox: (code: string, timeoutSeconds = 10, files: Record<string, string> = {}) =>
    request<SandboxResult>("/v1/sandbox/run", {
      method: "POST",
      body: JSON.stringify({ code, timeout_seconds: timeoutSeconds, files }),
    }),

  // ── M18: Bulk document operations ────────────────────────────────────────
  bulkDocuments: (payload: {
    document_ids: string[];
    action: "delete" | "set_tags" | "reindex";
    tags?: string[];
  }) =>
    request<{ succeeded: string[]; failed: Record<string, string>; action: string }>(
      "/v1/documents/bulk",
      { method: "POST", body: JSON.stringify(payload) }
    ),

  // ── M18: Conversation export ──────────────────────────────────────────────
  /** Returns the raw Response so the caller can handle filename + download. */
  exportConversation: async (conversationId: string, format: "json" | "markdown"): Promise<Blob> => {
    const response = await fetch(
      `/v1/conversations/${conversationId}/export?format=${format}`,
      { credentials: "include" }
    );
    if (!response.ok) throw new ApiError(await responseError(response), response.status);
    return response.blob();
  },

  // ── M18: Agent run export ─────────────────────────────────────────────────
  exportAgentRun: async (agentId: string, runId: string, format: "json" | "markdown"): Promise<Blob> => {
    const response = await fetch(
      `/v1/agents/${agentId}/runs/${runId}/export?format=${format}`,
      { credentials: "include" }
    );
    if (!response.ok) throw new ApiError(await responseError(response), response.status);
    return response.blob();
  },
};

export const sendChatMessage = api.chat;
