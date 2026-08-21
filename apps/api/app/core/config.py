from functools import lru_cache
from pathlib import Path

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

    database_url: str = (
        "postgresql+psycopg://promptforge:local-development-only@localhost:5432/promptforge"
    )
    cors_origins: list[str] = ["http://localhost:3000"]
    openai_api_key: SecretStr | None = None
    openai_model: str = "gpt-4.1-mini"
    openai_execution_model: str | None = None
    openai_timeout_seconds: float = Field(default=30.0, gt=0)
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

    @property
    def resolved_openai_execution_model(self) -> str:
        """Use a dedicated execution model when configured, else retain the existing default."""
        return self.openai_execution_model or self.openai_model

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

    @model_validator(mode="after")
    def validate_chunk_budgets(self) -> "Settings":
        if self.chunk_max_tokens < self.chunk_target_tokens:
            raise ValueError("CHUNK_MAX_TOKENS must be at least CHUNK_TARGET_TOKENS.")
        if self.chunk_overlap_tokens >= self.chunk_max_tokens:
            raise ValueError("CHUNK_OVERLAP_TOKENS must be smaller than CHUNK_MAX_TOKENS.")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
