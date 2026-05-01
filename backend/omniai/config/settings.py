from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = Field(default="Omni-AI", alias="APP_NAME")
    app_env: str = Field(default="development", alias="APP_ENV")
    http_port: int = Field(default=9380, alias="HTTP_PORT")
    api_cors_origins: str = Field(default="http://localhost:5173", alias="API_CORS_ORIGINS")

    db_url: str = Field(default="sqlite:///./omniai-dev.db", alias="DB_URL")
    db_echo: bool = Field(default=False, alias="DB_ECHO")
    auto_create_schema: bool = Field(default=True, alias="AUTO_CREATE_SCHEMA")

    redis_url: str | None = Field(default=None, alias="REDIS_URL")

    object_store_kind: str = Field(default="local", alias="OBJECT_STORE_KIND")
    object_store_endpoint: str | None = Field(default=None, alias="OBJECT_STORE_ENDPOINT")
    object_store_region: str = Field(default="us-east-1", alias="OBJECT_STORE_REGION")
    object_store_access_key: str | None = Field(default=None, alias="OBJECT_STORE_ACCESS_KEY")
    object_store_secret_key: str | None = Field(default=None, alias="OBJECT_STORE_SECRET_KEY")
    object_store_bucket: str = Field(default="omniai", alias="OBJECT_STORE_BUCKET")
    object_store_local_dir: str = Field(default="./.omniai-storage", alias="OBJECT_STORE_LOCAL_DIR")

    upload_max_bytes: int = Field(default=100 * 1024 * 1024, alias="UPLOAD_MAX_BYTES")
    worker_inline: bool = Field(default=False, alias="WORKER_INLINE")

    search_kind: str = Field(default="opensearch", alias="SEARCH_KIND")
    search_url: str | None = Field(default=None, alias="SEARCH_URL")
    search_snapshot_path: str | None = Field(default=None, alias="SEARCH_SNAPSHOT_PATH")

    reranker_kind: str = Field(default="paired", alias="RERANKER_KIND")
    reranker_model: str = Field(default="BAAI/bge-reranker-base", alias="RERANKER_MODEL")

    ocr_kind: str = Field(default="none", alias="OCR_KIND")
    ocr_min_chars_per_page: int = Field(default=50, alias="OCR_MIN_CHARS_PER_PAGE")
    ocr_image_dpi: int = Field(default=200, alias="OCR_IMAGE_DPI")
    ollama_vision_model: str = Field(default="llava", alias="OLLAMA_VISION_MODEL")

    sandbox_kind: str = Field(default="none", alias="SANDBOX_KIND")
    sandbox_default_timeout_seconds: float = Field(default=30.0, alias="SANDBOX_DEFAULT_TIMEOUT_SECONDS")

    retrieval_cache_ttl_seconds: int = Field(default=0, alias="RETRIEVAL_CACHE_TTL_SECONDS")

    rate_limit_per_minute: int = Field(default=120, alias="RATE_LIMIT_PER_MINUTE")
    tenant_max_documents: int = Field(default=10000, alias="TENANT_MAX_DOCUMENTS")
    tenant_max_storage_bytes: int = Field(default=50 * 1024 * 1024 * 1024, alias="TENANT_MAX_STORAGE_BYTES")

    ollama_base_url: str = Field(default="http://localhost:11434", alias="OLLAMA_BASE_URL")

    bootstrap_tenant_slug: str = Field(default="local-dev", alias="BOOTSTRAP_TENANT_SLUG")
    bootstrap_tenant_name: str = Field(default="Local Development Tenant", alias="BOOTSTRAP_TENANT_NAME")
    bootstrap_admin_email: str = Field(default="admin@omniai.local", alias="BOOTSTRAP_ADMIN_EMAIL")
    bootstrap_admin_password: str = Field(default="Admin12345!", alias="BOOTSTRAP_ADMIN_PASSWORD")
    bootstrap_admin_display_name: str = Field(default="Local Admin", alias="BOOTSTRAP_ADMIN_DISPLAY_NAME")

    auth_secret: str = Field(default="change-me-in-production", alias="AUTH_SECRET")
    encryption_key: str = Field(
        default="dev-only-do-not-use-in-prod-change-me-32b",
        alias="ENCRYPTION_KEY",
    )
    session_ttl_minutes: int = Field(default=480, alias="SESSION_TTL_MINUTES")
    session_cookie_name: str = Field(default="omniai_session", alias="SESSION_COOKIE_NAME")
    registration_open: bool = Field(default=True, alias="REGISTRATION_OPEN")
    login_lockout_threshold: int = Field(default=5, alias="LOGIN_LOCKOUT_THRESHOLD")
    login_lockout_minutes: int = Field(default=15, alias="LOGIN_LOCKOUT_MINUTES")
    # M15 — invitations
    invitation_expiry_hours: int = Field(default=72, alias="INVITATION_EXPIRY_HOURS")
    # M15 — OIDC / social login (per-provider; accessed via helpers below)
    google_client_id: str | None = Field(default=None, alias="GOOGLE_CLIENT_ID")
    google_client_secret: str | None = Field(default=None, alias="GOOGLE_CLIENT_SECRET")
    github_client_id: str | None = Field(default=None, alias="GITHUB_CLIENT_ID")
    github_client_secret: str | None = Field(default=None, alias="GITHUB_CLIENT_SECRET")
    microsoft_client_id: str | None = Field(default=None, alias="MICROSOFT_CLIENT_ID")
    microsoft_client_secret: str | None = Field(default=None, alias="MICROSOFT_CLIENT_SECRET")
    # M16 — OpenTelemetry
    otel_exporter_otlp_endpoint: str | None = Field(default=None, alias="OTEL_EXPORTER_OTLP_ENDPOINT")
    otel_service_name: str = Field(default="omniai-api", alias="OTEL_SERVICE_NAME")
    # M16 — Sentry
    sentry_dsn: str | None = Field(default=None, alias="SENTRY_DSN")
    sentry_traces_sample_rate: float = Field(default=0.1, alias="SENTRY_TRACES_SAMPLE_RATE")
    # M16 — cost tracking (price per 1k tokens in USD)
    llm_cost_per_1k_prompt: float = Field(default=0.002, alias="LLM_COST_PER_1K_PROMPT")
    llm_cost_per_1k_completion: float = Field(default=0.006, alias="LLM_COST_PER_1K_COMPLETION")

    # M17 — Connector Library: default credential env-vars (connectors can also
    # embed credentials directly in their config dict stored per-connector in DB).
    # Google Drive (service account JSON as a single-line string)
    gdrive_service_account_json: str | None = Field(default=None, alias="GDRIVE_SERVICE_ACCOUNT_JSON")
    # SharePoint / OneDrive — Azure AD app credentials
    sharepoint_tenant_id: str | None = Field(default=None, alias="SHAREPOINT_TENANT_ID")
    sharepoint_client_id: str | None = Field(default=None, alias="SHAREPOINT_CLIENT_ID")
    sharepoint_client_secret: str | None = Field(default=None, alias="SHAREPOINT_CLIENT_SECRET")
    # Notion integration token
    notion_api_key: str | None = Field(default=None, alias="NOTION_API_KEY")
    # Confluence
    confluence_base_url: str | None = Field(default=None, alias="CONFLUENCE_BASE_URL")
    confluence_api_token: str | None = Field(default=None, alias="CONFLUENCE_API_TOKEN")
    # Slack bot token
    slack_bot_token: str | None = Field(default=None, alias="SLACK_BOT_TOKEN")
    # Connector preview max items cap (server-side hard limit)
    connector_preview_max_items: int = Field(default=20, alias="CONNECTOR_PREVIEW_MAX_ITEMS")

    # M19 — Advanced Retrieval
    # HyDE: use a generative model to produce a hypothetical document before retrieval
    hyde_enabled: bool = Field(default=False, alias="HYDE_ENABLED")
    hyde_model: str = Field(default="", alias="HYDE_MODEL")  # "" = use collection default
    # pgvector adapter (SEARCH_KIND=pgvector uses DB_URL)
    pgvector_table: str = Field(default="omniai_vectors", alias="PGVECTOR_TABLE")
    # Pinecone adapter
    pinecone_api_key: str | None = Field(default=None, alias="PINECONE_API_KEY")
    pinecone_environment: str = Field(default="us-east-1-aws", alias="PINECONE_ENVIRONMENT")
    pinecone_index_name: str = Field(default="omniai", alias="PINECONE_INDEX_NAME")
    # Weaviate adapter
    weaviate_url: str = Field(default="http://localhost:8080", alias="WEAVIATE_URL")
    weaviate_api_key: str | None = Field(default=None, alias="WEAVIATE_API_KEY")
    weaviate_class_name: str = Field(default="OmniAIChunk", alias="WEAVIATE_CLASS_NAME")

    # ── M20: Agent Platform ───────────────────────────────────────────────────
    # Cost alerting: warn + emit event when a run exceeds this threshold (USD).
    # Set to 0 to disable.
    agent_run_cost_alert_usd: float = Field(default=0.0, alias="AGENT_RUN_COST_ALERT_USD")
    # Marketplace: base URL for template registry (can be an internal endpoint)
    agent_marketplace_url: str = Field(
        default="https://marketplace.omniai.dev/templates",
        alias="AGENT_MARKETPLACE_URL",
    )
    # gVisor: path to the runsc binary
    gvisor_runsc_bin: str = Field(default="runsc", alias="GVISOR_RUNSC_BIN")

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    @property
    def cors_origins(self) -> list[str]:
        return [origin.strip() for origin in self.api_cors_origins.split(",") if origin.strip()]

    def oidc_client_id(self, provider: str) -> str | None:
        return getattr(self, f"{provider.lower()}_client_id", None)

    def oidc_client_secret(self, provider: str) -> str | None:
        return getattr(self, f"{provider.lower()}_client_secret", None)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
