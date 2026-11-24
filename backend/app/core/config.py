from functools import lru_cache
from pathlib import Path
from urllib.parse import urlsplit

from cryptography.fernet import Fernet
from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT_ENV = Path(__file__).resolve().parents[2] / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT_ENV, env_file_encoding="utf-8", extra="ignore")

    mongodb_uri: str = "mongodb://localhost:27017"
    mongodb_database: str = "mindflow_ai"
    # Deployment environment: development | demo | production. Demo seeding
    # (NEXORA spec Part 5) is only allowed outside production.
    app_env: str = "development"
    jwt_secret: SecretStr
    credential_encryption_key: SecretStr | None = None
    cors_origins: list[str] = Field(
        default_factory=lambda: ["http://localhost:3000", "http://127.0.0.1:3000"]
    )
    cookie_secure: bool = False
    access_token_minutes: int = Field(default=15, ge=1, le=60)
    refresh_token_days: int = Field(default=7, ge=1, le=30)
    api_rate_limit: int = Field(default=120, ge=1)
    auth_rate_limit: int = Field(default=10, ge=1)
    rate_limit_window_seconds: int = Field(default=60, ge=1)
    # Phase 6 workflow budgets (per-agent Phase 5 limits stay in AgentLimits:
    # 6 steps, 120s, 8000 estimated tokens, 4 tools/step, 10s tool timeout).
    workflow_max_agent_turns: int = Field(default=12, ge=1, le=100)
    workflow_timeout_seconds: int = Field(default=600, ge=10)
    workflow_max_revisions_per_task: int = Field(default=2, ge=0, le=10)
    workflow_lease_seconds: int = Field(default=900, ge=30)
    workflow_context_chars_per_result: int = Field(default=2000, ge=100)
    # Website ZIP artifact limits (output_type="website_zip" workflows only).
    artifact_max_files: int = Field(default=50, ge=1, le=500)
    artifact_max_file_bytes: int = Field(default=262_144, ge=1024)
    artifact_max_total_bytes: int = Field(default=2_097_152, ge=1024)
    # MindFlow -> self-hosted n8n bridge (AI Factory page). Runs are
    # asynchronous: the backend fires the webhook of the user's own n8n
    # instance (default matches the docker-compose setup in n8n-ai-factory/,
    # n8n published on port 5678), n8n accepts immediately and executes in
    # the background, then calls the run's callback URL when finished.
    n8n_webhook_base_url: str = "http://localhost:5678"
    # Bounds only the fire-the-webhook call; workflow 07 answers as soon as
    # it has accepted the run, so this stays short.
    n8n_factory_timeout_seconds: int = Field(default=60, ge=10, le=600)
    # Base URL the n8n CONTAINER uses to call this backend back. Inside the
    # compose network the backend lives on the host, hence
    # host.docker.internal; override when the backend is bound elsewhere.
    n8n_factory_callback_base_url: str = "http://host.docker.internal:8000"
    # A run with no callback after this long is reported as failed
    # (run_timed_out) instead of spinning forever.
    n8n_factory_run_timeout_seconds: int = Field(default=1800, ge=120, le=86400)

    @field_validator("credential_encryption_key")
    @classmethod
    def validate_encryption_key(cls, value: SecretStr | None) -> SecretStr | None:
        if value is None or value.get_secret_value() == "":
            return None
        try:
            Fernet(value.get_secret_value().encode("ascii"))
        except (ValueError, UnicodeError):
            raise ValueError("CREDENTIAL_ENCRYPTION_KEY must be a Fernet key") from None
        return value

    @field_validator("jwt_secret")
    @classmethod
    def validate_secret(cls, value: SecretStr) -> SecretStr:
        secret = value.get_secret_value()
        placeholders = ("change", "replace", "placeholder", "your-secret", "your_secret")
        if (
            len(secret) < 32
            or len(set(secret)) < 8
            or any(word in secret.lower() for word in placeholders)
        ):
            raise ValueError("JWT_SECRET must be a random secret of at least 32 characters")
        return value

    @field_validator("app_env")
    @classmethod
    def validate_app_env(cls, value: str) -> str:
        normalized = value.strip().lower()
        if normalized not in {"development", "demo", "production"}:
            raise ValueError("APP_ENV must be development, demo or production")
        return normalized

    @field_validator("mongodb_uri")
    @classmethod
    def validate_mongodb_uri(cls, value: str) -> str:
        if not value.startswith(("mongodb://", "mongodb+srv://")):
            raise ValueError("MONGODB_URI must start with mongodb:// or mongodb+srv://")
        return value

    @field_validator("n8n_webhook_base_url", "n8n_factory_callback_base_url")
    @classmethod
    def validate_n8n_base_url(cls, value: str) -> str:
        parsed = urlsplit(value)
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.hostname
            or parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError(
                "n8n base URLs must be HTTP(S) origins without credentials"
            )
        return value.rstrip("/")

    @field_validator("cors_origins")
    @classmethod
    def validate_origins(cls, values: list[str]) -> list[str]:
        for value in values:
            parsed = urlsplit(value)
            if (
                parsed.scheme not in {"http", "https"}
                or not parsed.hostname
                or parsed.username
                or parsed.password
                or parsed.path
                or parsed.query
                or parsed.fragment
                or "*" in value
            ):
                raise ValueError("CORS_ORIGINS must contain explicit HTTP(S) origins without paths")
        return list(dict.fromkeys(values))


@lru_cache
def get_settings() -> Settings:
    return Settings()
