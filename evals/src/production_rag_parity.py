"""M6.1 probes for the configured production RAG path without model downloads."""

import inspect
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class ParityCheck:
    name: str
    passed: bool
    detail: str


class _Vector:
    def __init__(self, values: list[float]) -> None:
        self._values = values

    def tolist(self) -> list[float]:
        return self._values


class _RecordingEmbeddingModel:
    """SentenceTransformer-shaped probe used only to exercise the production adapter."""

    def __init__(self, dimension: int) -> None:
        self._dimension = dimension
        self.calls: list[tuple[object, dict[str, object]]] = []

    def get_embedding_dimension(self) -> int:
        return self._dimension

    def encode(self, value: object, **kwargs: object) -> _Vector:
        self.calls.append((value, kwargs))
        if isinstance(value, list):
            return _Vector([[1.0] + [0.0] * (self._dimension - 1) for _ in value])  # type: ignore[arg-type]
        return _Vector([1.0] + [0.0] * (self._dimension - 1))


def collect_production_parity() -> dict[str, Any]:
    """Exercise production boundaries and return a serializable M6.1 snapshot.

    Importing happens here so normal evaluation tooling remains usable without the
    API package on ``sys.path``. The probe never loads a Hugging Face model or a
    generation provider.
    """
    from app.core.config import Settings
    from app.document_processing.chunking import StructureAwareChunker
    from app.document_processing.models import ChunkingConfig
    from app.infrastructure.huggingface_embeddings import (
        E5_RETRIEVAL_INSTRUCTION,
        SELECTED_EMBEDDING_DIMENSION,
        MultilingualE5EmbeddingProvider,
    )
    from app.repositories.retrieval import DenseRetrievalRepository
    from app.services.context import ContextBuilder
    from app.services.rag import GroundedRagService
    from app.services.retrieval import RetrievedChunk
    from prompt_engine.execution import ExecutionResult

    settings = Settings()
    chunking_config = ChunkingConfig(
        target_tokens=settings.chunk_target_tokens,
        max_tokens=settings.chunk_max_tokens,
        overlap_tokens=settings.chunk_overlap_tokens,
    )
    chunker = StructureAwareChunker(chunking_config)
    provider = MultilingualE5EmbeddingProvider(
        model_id=settings.embedding_model_id,
        batch_size=settings.embedding_batch_size,
        device=settings.embedding_device,
        max_input_tokens=settings.embedding_max_input_tokens,
    )
    embedding_model = _RecordingEmbeddingModel(SELECTED_EMBEDDING_DIMENSION)
    provider._model = embedding_model
    passage = "Raw passage text; no retrieval prefix."
    query = "Which passage is relevant?"
    passage_vectors = provider.embed_passages([passage])
    query_vector = provider.embed_query(query)
    passage_value, passage_options = embedding_model.calls[0]
    query_value, query_options = embedding_model.calls[1]

    chunk = RetrievedChunk(
        chunk_id="m6-chunk-1",
        document_id="m6-document-1",
        filename="m6.txt",
        chunk_index=0,
        text="The verified launch date is Monday.",
        distance=0.1,
        similarity=0.9,
        page_start=1,
        page_end=1,
        section="Timeline",
        heading="Launch",
        source_block_start=0,
        source_block_end=0,
    )
    context_builder = ContextBuilder(max_tokens=settings.rag_context_max_tokens)
    context = context_builder.build([chunk])

    class _RetrievalProbe:
        def __init__(self, results: list[RetrievedChunk]) -> None:
            self.results = results
            self.calls = 0

        def search(self, **_: object) -> list[RetrievedChunk]:
            self.calls += 1
            return self.results

    class _GenerationProbe:
        def __init__(self) -> None:
            self.calls = 0

        def execute(self, _: str) -> ExecutionResult:
            self.calls += 1
            return ExecutionResult(output="The launch date is Monday. [1]")

    retrieval_probe = _RetrievalProbe([chunk])
    generation_probe = _GenerationProbe()
    answer = GroundedRagService(
        retrieval_service=retrieval_probe,  # type: ignore[arg-type]
        context_builder=context_builder,
        generation_backend=generation_probe,
    ).ask(query="When is the launch?")
    insufficient_generation = _GenerationProbe()
    insufficient_retrieval = _RetrievalProbe([])
    insufficient = GroundedRagService(
        retrieval_service=insufficient_retrieval,  # type: ignore[arg-type]
        context_builder=context_builder,
        generation_backend=insufficient_generation,
    ).ask(query="What is not available?")

    postgres_source = inspect.getsource(DenseRetrievalRepository._search_postgres)
    repository_source = inspect.getsource(DenseRetrievalRepository.search)
    normalized_options = {"normalize_embeddings": True, "show_progress_bar": False}
    checks = (
        ParityCheck(
            "production_chunker_config",
            chunker._config == ChunkingConfig(350, 500, 40),
            "StructureAwareChunker uses target/max/overlap 350/500/40.",
        ),
        ParityCheck(
            "embedding_model",
            provider.model_id == "intfloat/multilingual-e5-large-instruct",
            "Production embedding provider uses the M4-selected multilingual E5 model.",
        ),
        ParityCheck(
            "e5_passage_format_and_normalization",
            passage_value == [passage]
            and passage_options
            == {"batch_size": settings.embedding_batch_size, **normalized_options}
            and len(passage_vectors[0]) == SELECTED_EMBEDDING_DIMENSION,
            "Passages are raw and normalized to 1024 dimensions.",
        ),
        ParityCheck(
            "e5_query_format_and_normalization",
            query_value == f"Instruct: {E5_RETRIEVAL_INSTRUCTION}\nQuery: {query}"
            and query_options == normalized_options
            and len(query_vector) == SELECTED_EMBEDDING_DIMENSION,
            "Queries use the selected instructed E5 format and normalized vectors.",
        ),
        ParityCheck(
            "pgvector_cosine_hnsw_query",
            "<=>" in postgres_source and "hnsw.ef_search" in postgres_source,
            "PostgreSQL retrieval uses pgvector cosine distance with HNSW settings.",
        ),
        ParityCheck(
            "workspace_filter_before_results",
            "DocumentEmbeddingRecord.workspace_id == workspace_id" in repository_source,
            "Workspace scope is a SQL filter before rows are ranked or returned.",
        ),
        ParityCheck(
            "production_context_builder",
            context.state == "ready" and context.sources[0].citation_id == 1,
            "Production ContextBuilder creates the cited ContextPackage source.",
        ),
        ParityCheck(
            "single_pass_grounded_ask",
            retrieval_probe.calls == 1 and generation_probe.calls == 1,
            "A ready ask performs one retrieval and one generation.",
        ),
        ParityCheck(
            "insufficient_evidence_skips_generation",
            insufficient.state == "insufficient_evidence"
            and insufficient_retrieval.calls == 1
            and insufficient_generation.calls == 0,
            "Insufficient evidence produces no generation call.",
        ),
        ParityCheck(
            "citation_provenance_mapping",
            answer.answer is not None
            and "[1]" in answer.answer
            and len(answer.sources) == 1
            and answer.sources[0].citation_id == 1
            and answer.sources[0].chunk_id == chunk.chunk_id,
            "Citation [1] maps only to the included production ContextPackage source.",
        ),
    )
    return {
        "schemaVersion": "m6.1",
        "status": "passed" if all(check.passed for check in checks) else "failed",
        "productionConfiguration": {
            "chunker": {
                "implementation": "app.document_processing.chunking.StructureAwareChunker",
                "targetTokens": chunking_config.target_tokens,
                "maxTokens": chunking_config.max_tokens,
                "overlapTokens": chunking_config.overlap_tokens,
            },
            "embedding": {
                "modelId": provider.model_id,
                "dimension": SELECTED_EMBEDDING_DIMENSION,
                "passageFormat": "raw_text",
                "queryFormat": f"Instruct: {E5_RETRIEVAL_INSTRUCTION}\\nQuery: <query>",
                "normalizeEmbeddings": True,
            },
            "retrieval": {
                "database": "PostgreSQL + pgvector",
                "distance": "cosine (<=>)",
            },
        },
        "checks": [asdict(check) for check in checks],
        "postgresPgvectorSmoke": {
            "status": "not_run",
            "reason": "Requires an explicitly provisioned PostgreSQL + pgvector database.",
            "command": (
                "RUN_PGVECTOR_SMOKE=1 PGVECTOR_SMOKE_DATABASE_URL=<postgresql+psycopg URL> "
                "PYTHONPATH=apps/api python -m pytest "
                "apps/api/tests/test_pgvector_smoke.py -q"
            ),
        },
        "knownLimitations": [
            "This is configuration and infrastructure parity validation, not answer-quality scoring.",
            "The default unit suite uses fake embeddings and generation; it does not download a model or call a provider.",
            "The PostgreSQL smoke test must run against a separately migrated pgvector database.",
        ],
    }


def write_production_parity_artifacts(output_dir: Path) -> dict[str, Any]:
    """Write the static parity snapshot and a concise human-readable summary."""
    payload = collect_production_parity()
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "production_rag_parity_v1.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    checks = "\n".join(
        f"- {'PASS' if check['passed'] else 'FAIL'} — `{check['name']}`: {check['detail']}"
        for check in payload["checks"]
    )
    smoke = payload["postgresPgvectorSmoke"]
    (output_dir / "production_rag_parity_v1.md").write_text(
        "# M6.1 production RAG parity validation\n\n"
        f"Static parity status: **{payload['status']}**.\n\n"
        "## Checks\n\n"
        f"{checks}\n\n"
        "## PostgreSQL + pgvector smoke\n\n"
        f"Status: **{smoke['status']}** — {smoke['reason']}\n\n"
        "Run after applying migrations to an isolated smoke database:\n\n"
        f"```bash\n{smoke['command']}\n```\n\n"
        "## Limitations\n\n"
        + "\n".join(f"- {item}" for item in payload["knownLimitations"])
        + "\n",
        encoding="utf-8",
    )
    return payload


if __name__ == "__main__":
    write_production_parity_artifacts(Path("evals/results/final"))
