from functools import lru_cache

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

API_PREFIX = "/api"
DEFAULT_DATABASE_URL = "postgresql+psycopg://gridline:gridline@localhost:5432/gridline"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=(".env", "../../.env"), extra="ignore")

    environment: str = "development"
    database_url: str = DEFAULT_DATABASE_URL
    public_api_base_url: str = "http://localhost:8000"
    cors_origins: str = "http://localhost:3000"
    log_level: str = "INFO"

    sync_interval_minutes: int = 30
    source_timeout_seconds: int = 240  # per-source wall clock budget (fetch + parse)
    entries_timeout_seconds: int = 900  # entry lists need many polite requests (WEC: one per car and driver)
    entries_settle_days: int = 14  # finished events with stored live entries are not re-fetched after this
    sync_min_ratio: float = 0.5
    # Keep the lease TTL comfortably above the heartbeat interval.
    sync_lease_ttl_seconds: int = 300
    sync_lease_heartbeat_seconds: int = 60
    sync_lease_max_heartbeat_failures: int = 3  # consecutive failed renewals (database errors) before the lease counts as lost

    source_healthy_max_age_minutes: int = 90  # last successful live sync no older than this => healthy
    source_failing_after_failures: int = 2  # consecutive failed live runs => failing
    source_run_retention_days: int = 30

    feed_lookback_days: int = 14
    feed_rate_limit_per_minute: int = 10  # POST/PATCH/DELETE /feeds per client IP
    trust_proxy_headers: bool = False  # honour X-Forwarded-For (only behind a trusted reverse proxy)

    @model_validator(mode="after")
    def _production_checks(self) -> "Settings":
        if self.environment == "production":
            if self.database_url == DEFAULT_DATABASE_URL or "localhost" in self.database_url:
                raise ValueError("DATABASE_URL must point at the production database (not the local default)")
            if not self.database_url.startswith("postgresql+psycopg://"):
                raise ValueError("DATABASE_URL must be a SQLAlchemy psycopg URL: postgresql+psycopg://…")
            origins = [o.strip() for o in self.cors_origins.split(",") if o.strip()]
            if not origins or "*" in origins:
                raise ValueError("CORS_ORIGINS must list explicit origins in production (no '*')")
            if self.public_api_base_url.startswith("http://localhost"):
                raise ValueError("PUBLIC_API_BASE_URL must be set to the public API URL in production")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
