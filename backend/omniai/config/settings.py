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

    search_kind: str = Field(default="opensearch", alias="SEARCH_KIND")
    search_url: str | None = Field(default=None, alias="SEARCH_URL")

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

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    @property
    def cors_origins(self) -> list[str]:
        return [origin.strip() for origin in self.api_cors_origins.split(",") if origin.strip()]


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
