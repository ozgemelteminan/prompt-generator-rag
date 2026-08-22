"""Hugging Face implementation of the production passage embedding contract."""

from app.services.embeddings import EmbeddingProviderError, EmbeddingProviderUnavailableError

SELECTED_EMBEDDING_DIMENSION = 1024
E5_RETRIEVAL_INSTRUCTION = (
    "Given a web search query, retrieve relevant passages that answer the query"
)


class MultilingualE5EmbeddingProvider:
    """Lazy, normalized raw-passage embeddings for multilingual-e5-large-instruct."""

    def __init__(
        self,
        *,
        model_id: str,
        batch_size: int,
        device: str | None = None,
        max_input_tokens: int | None = None,
    ) -> None:
        self._model_id = model_id
        self._batch_size = batch_size
        self._device = device
        self._max_input_tokens = max_input_tokens
        self._model: object | None = None

    @property
    def model_id(self) -> str:
        return self._model_id

    @property
    def dimension(self) -> int:
        model = self._load_model()
        return int(model.get_embedding_dimension())  # type: ignore[union-attr]

    def embed_passages(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        model = self._load_model()
        try:
            vectors = model.encode(  # type: ignore[union-attr]
                texts,
                batch_size=self._batch_size,
                normalize_embeddings=True,
                show_progress_bar=False,
            )
        except Exception as error:
            raise EmbeddingProviderError("Passage embedding failed.") from error
        return [[float(value) for value in vector] for vector in vectors.tolist()]

    def embed_query(self, text: str) -> list[float]:
        """Embed one E5-instruct query; passages deliberately remain raw text."""
        model = self._load_model()
        formatted_query = f"Instruct: {E5_RETRIEVAL_INSTRUCTION}\nQuery: {text}"
        try:
            vector = model.encode(  # type: ignore[union-attr]
                formatted_query,
                normalize_embeddings=True,
                show_progress_bar=False,
            )
        except Exception as error:
            raise EmbeddingProviderError("Query embedding failed.") from error
        return [float(value) for value in vector.tolist()]

    def _load_model(self) -> object:
        if self._model is not None:
            return self._model
        try:
            from sentence_transformers import SentenceTransformer

            self._model = SentenceTransformer(self._model_id, device=self._device)
            if self._max_input_tokens is not None:
                self._model.max_seq_length = self._max_input_tokens
        except Exception as error:
            raise EmbeddingProviderUnavailableError("Embedding model is unavailable.") from error
        return self._model
