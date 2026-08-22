"""Evaluation-local timing and operational checks for the production RAG path."""

import argparse
import csv
import json
import math
import statistics
import time
from collections import defaultdict
from collections.abc import Callable, Iterable
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class PriceAssumption:
    input_per_million: float
    output_per_million: float
    currency: str
    as_of: str


@dataclass(frozen=True)
class TokenUsage:
    input_tokens: int | None
    output_tokens: int | None
    generation_calls: int


class TimingCollector:
    def __init__(self, clock: Callable[[], float] = time.perf_counter) -> None:
        self._clock = clock
        self.values: defaultdict[str, list[float]] = defaultdict(list)

    def measure(self, name: str, operation: Callable[[], Any]) -> Any:
        started = self._clock()
        try:
            return operation()
        finally:
            self.values[name].append((self._clock() - started) * 1_000)


def summarize_latency(samples_ms: Iterable[float]) -> dict[str, float | int | None]:
    values = sorted(samples_ms)
    if not values:
        return {
            "count": 0,
            "mean_ms": None,
            "p50_ms": None,
            "p95_ms": None,
            "min_ms": None,
            "max_ms": None,
        }
    return {
        "count": len(values),
        "mean_ms": statistics.fmean(values),
        "p50_ms": _nearest_rank(values, 0.50),
        "p95_ms": _nearest_rank(values, 0.95),
        "min_ms": values[0],
        "max_ms": values[-1],
    }


def _nearest_rank(values: list[float], percentile: float) -> float:
    return values[max(0, math.ceil(percentile * len(values)) - 1)]


def aggregate_token_usage(
    usages: Iterable[TokenUsage], *, price: PriceAssumption | None = None
) -> dict[str, int | float | str | None]:
    values = tuple(usages)
    inputs = [usage.input_tokens for usage in values]
    outputs = [usage.output_tokens for usage in values]
    input_tokens = sum(inputs) if all(value is not None for value in inputs) else None
    output_tokens = (
        sum(outputs) if all(value is not None for value in outputs) else None
    )
    total_tokens = (
        input_tokens + output_tokens
        if input_tokens is not None and output_tokens is not None
        else None
    )
    estimated_cost = (
        input_tokens / 1_000_000 * price.input_per_million
        + output_tokens / 1_000_000 * price.output_per_million
        if price is not None and input_tokens is not None and output_tokens is not None
        else None
    )
    return {
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": total_tokens,
        "generation_calls": sum(usage.generation_calls for usage in values),
        "estimated_cost": estimated_cost,
        "currency": price.currency
        if estimated_cost is not None and price is not None
        else None,
        "price_assumption": asdict(price) if price is not None else None,
    }


class _TimedEmbeddingProvider:
    def __init__(self, provider: Any, timings: TimingCollector) -> None:
        self._provider = provider
        self._timings = timings
        self.query_calls = 0

    @property
    def model_id(self) -> str:
        return self._provider.model_id

    @property
    def dimension(self) -> int:
        return self._provider.dimension

    def embed_query(self, text: str) -> list[float]:
        self.query_calls += 1
        return self._timings.measure(
            "query_embedding", lambda: self._provider.embed_query(text)
        )

    def embed_passages(self, texts: list[str]) -> list[list[float]]:
        return self._provider.embed_passages(texts)


class _TimedRetrievalRepository:
    def __init__(self, repository: Any, timings: TimingCollector) -> None:
        self._repository = repository
        self._timings = timings
        self.calls = 0

    def search(self, **kwargs: Any) -> Any:
        self.calls += 1
        return self._timings.measure(
            "retrieval", lambda: self._repository.search(**kwargs)
        )


class _TimedContextBuilder:
    def __init__(self, builder: Any, timings: TimingCollector) -> None:
        self._builder = builder
        self._timings = timings
        self.calls = 0
        self.last_package: Any | None = None

    def build(self, results: Any) -> Any:
        self.calls += 1
        self.last_package = self._timings.measure(
            "context_build", lambda: self._builder.build(results)
        )
        return self.last_package


class _TimedGenerationBackend:
    def __init__(self, backend: Any, timings: TimingCollector) -> None:
        self._backend = backend
        self._timings = timings
        self.calls = 0

    def execute(self, prompt: str) -> Any:
        self.calls += 1
        return self._timings.measure(
            "generation", lambda: self._backend.execute(prompt)
        )


def run_deterministic_local() -> dict[str, Any]:
    """Exercise production service boundaries without model, provider, or network calls."""
    from app.core.config import Settings

    settings = Settings()
    success = _run_local_ask(has_evidence=True)
    insufficient = _run_local_ask(has_evidence=False)
    return {
        "status": "completed",
        "latency": {
            name: summarize_latency(samples)
            for name, samples in success["timings"].items()
        },
        "successfulAsk": success["invariants"],
        "insufficientEvidence": insufficient["invariants"],
        "operationalChecks": {
            "context_budget_bounded": success["context_token_count"]
            <= success["context_budget"],
            "retrieval_limit_bounded": settings.retrieval_default_limit
            <= settings.retrieval_max_limit,
            "timeout_configured": settings.llm_timeout_seconds > 0,
            "public_sources_exclude_vectors_and_storage": success["public_source_safe"],
            "provider_failure_sanitized": _provider_failure_is_sanitized(),
        },
        "tokenCost": aggregate_token_usage(
            [TokenUsage(None, None, success["generation_calls"])]
        ),
    }


def _run_local_ask(*, has_evidence: bool) -> dict[str, Any]:
    from app.core.caller import CallerContext
    from app.db.models import Base
    from app.infrastructure.huggingface_embeddings import SELECTED_EMBEDDING_DIMENSION
    from app.repositories.documents import DocumentRepository
    from app.repositories.retrieval import DenseRetrievalRepository
    from app.services.context import ContextBuilder
    from app.services.rag import GroundedRagService
    from app.services.retrieval import DenseRetrievalService
    from prompt_engine.execution import ExecutionResult
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session
    from sqlalchemy.pool import StaticPool

    class _Embedding:
        model_id = "intfloat/multilingual-e5-large-instruct"
        dimension = SELECTED_EMBEDDING_DIMENSION

        def embed_query(self, _: str) -> list[float]:
            return [1.0] + [0.0] * (self.dimension - 1)

        def embed_passages(self, _: list[str]) -> list[list[float]]:
            raise AssertionError("Operational probe only embeds its query.")

    class _Generation:
        def execute(self, _: str) -> ExecutionResult:
            return ExecutionResult(output="The evidence is available. [1]")

    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    session = Session(engine)
    try:
        Base.metadata.create_all(engine)
        if has_evidence:
            _add_local_embedding(session)
        timings = TimingCollector()
        embedding = _TimedEmbeddingProvider(_Embedding(), timings)
        repository = _TimedRetrievalRepository(
            DenseRetrievalRepository(session), timings
        )
        context = _TimedContextBuilder(ContextBuilder(max_tokens=200), timings)
        generation = _TimedGenerationBackend(_Generation(), timings)
        service = GroundedRagService(
            retrieval_service=DenseRetrievalService(
                caller=CallerContext("local-workspace"),
                document_repository=DocumentRepository(session),
                retrieval_repository=repository,
                embedding_provider=embedding,
                default_limit=1,
                max_limit=2,
                expected_dimension=SELECTED_EMBEDDING_DIMENSION,
                hnsw_ef_search=100,
            ),
            context_builder=context,
            generation_backend=generation,
        )
        result = timings.measure(
            "total_ask", lambda: service.ask(query="What evidence exists?")
        )
        expected_generation = 1 if has_evidence else 0
        sources = result.sources
        invariants = {
            "query_embedding_calls": embedding.query_calls,
            "retrieval_calls": repository.calls,
            "context_build_calls": context.calls,
            "generation_calls": generation.calls,
            "passed": (
                embedding.query_calls == 1
                and repository.calls == 1
                and context.calls == 1
                and generation.calls == expected_generation
                and result.state
                == ("answer" if has_evidence else "insufficient_evidence")
            ),
        }
        return {
            "timings": dict(timings.values),
            "invariants": invariants,
            "generation_calls": generation.calls,
            "context_token_count": context.last_package.token_count,
            "context_budget": 200,
            "retrieval_default_limit": 1,
            "retrieval_max_limit": 2,
            "public_source_safe": all(
                "embedding" not in source.__dict__ and "storage" not in source.__dict__
                for source in sources
            ),
        }
    finally:
        session.close()
        engine.dispose()


def _add_local_embedding(session: Any) -> None:
    from app.db.models import (
        DocumentChunkRecord,
        DocumentEmbeddingRecord,
        DocumentRecord,
    )
    from app.infrastructure.huggingface_embeddings import SELECTED_EMBEDDING_DIMENSION

    session.add(
        DocumentRecord(
            id="m64-document",
            workspace_id="local-workspace",
            original_filename="operational.txt",
            media_type="text/plain",
            file_size=12,
            checksum="a" * 64,
            ingestion_status="embedded",
            storage_key="m6/operational.txt",
        )
    )
    session.add(
        DocumentChunkRecord(
            id="m64-chunk",
            workspace_id="local-workspace",
            document_id="m64-document",
            chunk_index=0,
            text="The evidence is available.",
            token_count=5,
            language="en",
            page_start=1,
            page_end=1,
            section="Operations",
            heading="Operations",
            source_block_start=0,
            source_block_end=0,
        )
    )
    session.add(
        DocumentEmbeddingRecord(
            id="m64-embedding",
            workspace_id="local-workspace",
            document_id="m64-document",
            chunk_id="m64-chunk",
            embedding=[1.0] + [0.0] * (SELECTED_EMBEDDING_DIMENSION - 1),
            embedding_model_id="intfloat/multilingual-e5-large-instruct",
            embedding_dimension=SELECTED_EMBEDDING_DIMENSION,
        )
    )
    session.commit()


def _provider_failure_is_sanitized() -> bool:
    from app.services.context import ContextBuilder
    from app.services.rag import GroundedRagService, RagGenerationError
    from app.services.retrieval import RetrievedChunk
    from prompt_engine.errors import ExecutionBackendError

    class _Retrieval:
        def search(self, **_: Any) -> list[RetrievedChunk]:
            return [
                RetrievedChunk(
                    chunk_id="failure-chunk",
                    document_id="failure-document",
                    filename="failure.txt",
                    chunk_index=0,
                    text="Evidence",
                    distance=0.1,
                    similarity=0.9,
                    page_start=None,
                    page_end=None,
                    section=None,
                    heading=None,
                    source_block_start=0,
                    source_block_end=0,
                )
            ]

    class _Failure:
        def execute(self, _: str) -> object:
            raise ExecutionBackendError("raw-provider-token")

    try:
        GroundedRagService(
            retrieval_service=_Retrieval(),  # type: ignore[arg-type]
            context_builder=ContextBuilder(max_tokens=200),
            generation_backend=_Failure(),
        ).ask(query="query")
    except RagGenerationError as error:
        return "raw-provider-token" not in str(error)
    return False


def run_real_production(*, query: str, document_ids: tuple[str, ...]) -> dict[str, Any]:
    """One opt-in production request; requires configured PostgreSQL, model, and provider."""
    from app.api.v1.dependencies import get_embedding_provider
    from app.core.caller import CallerContext
    from app.core.config import Settings
    from app.db.session import SessionLocal
    from app.infrastructure.huggingface_embeddings import SELECTED_EMBEDDING_DIMENSION
    from app.infrastructure.llm import ProviderConfigurationError, create_llm_provider
    from app.repositories.documents import DocumentRepository
    from app.repositories.retrieval import DenseRetrievalRepository
    from app.services.context import ContextBuilder
    from app.services.rag import GroundedRagService
    from app.services.retrieval import DenseRetrievalService

    settings = Settings()
    try:
        backend = create_llm_provider(settings)
    except ProviderConfigurationError as error:
        raise ValueError(str(error)) from error
    session = SessionLocal()
    try:
        timings = TimingCollector()
        embedding = _TimedEmbeddingProvider(get_embedding_provider(settings), timings)
        repository = _TimedRetrievalRepository(
            DenseRetrievalRepository(session), timings
        )
        context = _TimedContextBuilder(
            ContextBuilder(max_tokens=settings.rag_context_max_tokens), timings
        )
        generation = _TimedGenerationBackend(
            backend,
            timings,
        )
        service = GroundedRagService(
            retrieval_service=DenseRetrievalService(
                caller=CallerContext(settings.local_workspace_id),
                document_repository=DocumentRepository(session),
                retrieval_repository=repository,
                embedding_provider=embedding,
                default_limit=settings.retrieval_default_limit,
                max_limit=settings.retrieval_max_limit,
                expected_dimension=SELECTED_EMBEDDING_DIMENSION,
                hnsw_ef_search=settings.hnsw_ef_search,
            ),
            context_builder=context,
            generation_backend=generation,
        )
        result = timings.measure(
            "total_ask", lambda: service.ask(query=query, document_ids=document_ids)
        )
        return {
            "status": "completed",
            "answer_state": result.state,
            "source_count": len(result.sources),
            "latency": {
                name: summarize_latency(samples)
                for name, samples in timings.values.items()
            },
            "requestCounts": {
                "query_embedding": embedding.query_calls,
                "retrieval": repository.calls,
                "context_build": context.calls,
                "generation": generation.calls,
            },
            "tokenCost": aggregate_token_usage(
                [TokenUsage(None, None, generation.calls)]
            ),
            "note": "The current production execution adapter exposes no token usage metadata; cost is price-dependent and unavailable.",
        }
    finally:
        session.close()


def write_operational_artifacts(
    local: dict[str, Any], *, output_dir: Path, real: dict[str, Any] | None = None
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "experimentVersion": "m6.4",
        "deterministicLocal": local,
        "realRun": real
        or {
            "status": "not_run",
            "command": "PYTHONPATH=apps/api:packages/prompt-engine python -m evals.src.operational_eval --mode real --query '<question>' --document-id '<embedded-document-id>'",
            "requirements": [
                "DATABASE_URL to migrated PostgreSQL + pgvector",
                "embedded scoped document",
                "selected LLM_PROVIDER configuration",
                "local E5 model runtime",
            ],
        },
        "limitations": [
            "Local timings are deterministic-fixture measurements, not production latency targets.",
            "Current provider adapters do not expose usage metadata through the provider-neutral contract, so token totals and cost remain unavailable.",
            "No provider prices are hardcoded; an estimate requires an explicit external price assumption.",
        ],
    }
    (output_dir / "operational_eval_v1.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    rows = [{"phase": name, **summary} for name, summary in local["latency"].items()]
    with (output_dir / "operational_eval_v1.csv").open(
        "w", encoding="utf-8", newline=""
    ) as file:
        writer = csv.DictWriter(
            file,
            fieldnames=(
                "phase",
                "count",
                "mean_ms",
                "p50_ms",
                "p95_ms",
                "min_ms",
                "max_ms",
            ),
        )
        writer.writeheader()
        writer.writerows(rows)
    summary_rows = "\n".join(
        f"| {row['phase']} | {row['count']} | {row['mean_ms']:.3f} | {row['p50_ms']:.3f} | {row['p95_ms']:.3f} |"
        for row in rows
    )
    checks = "\n".join(
        f"- `{name}`: {'passed' if passed else 'failed'}"
        for name, passed in local["operationalChecks"].items()
    )
    real_section = f"Status: **{payload['realRun']['status']}**.\n"
    if payload["realRun"].get("status") == "not_run":
        real_section += (
            "\n```bash\n"
            + payload["realRun"]["command"]
            + "\n```\n\nRequirements: "
            + "; ".join(payload["realRun"]["requirements"])
            + ".\n"
        )
    (output_dir / "operational_eval_v1.md").write_text(
        "# M6.4 RAG operational validation\n\n"
        "## Deterministic/local latency\n\n| Phase | Count | Mean ms | P50 ms | P95 ms |\n| --- | ---: | ---: | ---: | ---: |\n"
        f"{summary_rows}\n\n"
        "## Request-count invariants\n\n"
        f"- Successful ask: {local['successfulAsk']}\n"
        f"- Insufficient evidence: {local['insufficientEvidence']}\n\n"
        "## Operational checks\n\n"
        f"{checks}\n\n"
        "## Token and cost accounting\n\n"
        f"{local['tokenCost']}\n\n"
        "## Real run\n\n"
        f"{real_section}\n"
        "## Limitations\n\n"
        + "\n".join(f"- {item}" for item in payload["limitations"])
        + "\n",
        encoding="utf-8",
    )
    return payload


def _main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=("local", "real"), default="local")
    parser.add_argument("--query")
    parser.add_argument("--document-id", action="append", default=[])
    parser.add_argument("--output-dir", type=Path, default=Path("evals/results/final"))
    args = parser.parse_args()
    local = run_deterministic_local()
    real = None
    if args.mode == "real":
        if not args.query:
            raise ValueError("--query is required for --mode real.")
        real = run_real_production(
            query=args.query, document_ids=tuple(args.document_id)
        )
    write_operational_artifacts(local, output_dir=args.output_dir, real=real)


if __name__ == "__main__":
    _main()
