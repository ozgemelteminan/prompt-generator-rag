from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

REPOSITORY_ROOT = Path(__file__).resolve().parents[4]


class Settings(BaseSettings):
    """Runtime settings loaded from the environment or repository .env file."""

    model_config = SettingsConfigDict(
        env_file=REPOSITORY_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_environment: Literal["development", "production"] = "development"
    debug: bool = False
    database_url: str = (
        "postgresql+psycopg://promptforge:local-development-only@localhost:5432/promptforge"
    )
    cors_origins: list[str] = ["http://localhost:3000"]
    llm_provider: Literal["groq", "gemini"] = "groq"
    groq_api_key: SecretStr | None = None
    groq_model: str = "openai/gpt-oss-120b"
    gemini_api_key: SecretStr | None = None
    gemini_model: str | None = None
    llm_timeout_seconds: float = Field(default=30.0, gt=0)
    execution_max_input_characters: int = Field(default=20_000, gt=0)
    local_workspace_id: str = Field(default="local-workspace", min_length=1)
    rate_limit_generate_requests: int = Field(default=10, gt=0)
    rate_limit_execute_requests: int = Field(default=20, gt=0)
    rate_limit_window_seconds: int = Field(default=60, gt=0)
    generation_quota_per_month: int = Field(default=100, ge=0)
    execution_quota_per_month: int = Field(default=200, ge=0)
    document_max_upload_bytes: int = Field(default=10 * 1024 * 1024, gt=0)
    document_storage_path: Path = REPOSITORY_ROOT / "data" / "uploads"
    chunk_target_tokens: int = Field(default=350, gt=0)
    chunk_max_tokens: int = Field(default=500, gt=0)
    chunk_overlap_tokens: int = Field(default=40, ge=0)
    embedding_model_id: str = "intfloat/multilingual-e5-large-instruct"
    embedding_batch_size: int = Field(default=32, gt=0)
    embedding_device: str | None = None
    embedding_max_input_tokens: int | None = Field(default=None, gt=0)
    retrieval_default_limit: int = Field(default=5, gt=0)
    retrieval_max_limit: int = Field(default=20, gt=0)
    hnsw_ef_search: int = Field(default=100, gt=0)
    rag_context_max_tokens: int = Field(default=2_000, gt=0)

    @field_validator("cors_origins", mode="before")
    @classmethod
    def parse_cors_origins(cls, value: str | list[str]) -> list[str]:
        if isinstance(value, str):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value

    @field_validator("document_storage_path", mode="before")
    @classmethod
    def resolve_document_storage_path(cls, value: str | Path) -> Path:
        path = Path(value)
        return path if path.is_absolute() else REPOSITORY_ROOT / path

    @field_validator("embedding_device", mode="before")
    @classmethod
    def normalize_embedding_device(cls, value: str | None) -> str | None:
        return value.strip() or None if isinstance(value, str) else value

    @field_validator("groq_api_key", "gemini_api_key", "gemini_model", mode="before")
    @classmethod
    def normalize_optional_provider_values(cls, value: str | None) -> str | None:
        return value.strip() or None if isinstance(value, str) else value

    @model_validator(mode="after")
    def validate_chunk_budgets(self) -> "Settings":
        if self.app_environment == "production" and self.debug:
            raise ValueError("DEBUG must be false in production.")
        if "*" in self.cors_origins:
            raise ValueError("CORS_ORIGINS must list explicit origins.")
        if self.chunk_max_tokens < self.chunk_target_tokens:
            raise ValueError("CHUNK_MAX_TOKENS must be at least CHUNK_TARGET_TOKENS.")
        if self.chunk_overlap_tokens >= self.chunk_max_tokens:
            raise ValueError("CHUNK_OVERLAP_TOKENS must be smaller than CHUNK_MAX_TOKENS.")
        if self.retrieval_default_limit > self.retrieval_max_limit:
            raise ValueError("RETRIEVAL_DEFAULT_LIMIT must not exceed RETRIEVAL_MAX_LIMIT.")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
