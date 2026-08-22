"""Provider-independent contracts for production passage and query embeddings."""

from typing import Protocol


class EmbeddingProvider(Protocol):
    """Embed raw document passages without exposing a model implementation."""

    @property
    def model_id(self) -> str: ...

    @property
    def dimension(self) -> int: ...

    def embed_passages(self, texts: list[str]) -> list[list[float]]: ...

    def embed_query(self, text: str) -> list[float]: ...


class EmbeddingProviderUnavailableError(Exception):
    """Raised when the configured embedding model cannot be loaded."""


class EmbeddingProviderError(Exception):
    """Raised when an embedding request cannot be completed safely."""
