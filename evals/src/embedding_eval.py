"""M4.2 embedding-only benchmark over frozen production chunks."""

import csv
import gc
import json
import math
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol

from app.document_processing.models import ChunkingConfig

from evals.src.chunking_eval import EvaluationChunk, production_structure_aware_chunks
from evals.src.dataset import EvaluationDataset, EvaluationQuery
from evals.src.metrics import (
    aggregate_rankings,
    required_block_coverage_at_k,
)

E5_INSTRUCTION = "Instruct: Given a web search query, retrieve relevant passages that answer the query"
TURKISH_E5_INSTRUCTION = (
    "Given a Turkish search query, retrieve relevant passages written in Turkish "
    "that best answer the query"
)


@dataclass(frozen=True)
class EmbeddingModelSpec:
    key: str
    model_id: str
    query_formatter: Callable[[str], str]
    passage_formatter: Callable[[str], str]
    normalize_embeddings: bool
    max_sequence_length: int | None = None
    trust_remote_code: bool = False


def embedding_model_registry() -> dict[str, EmbeddingModelSpec]:
    return {
        "gte_multilingual_base": EmbeddingModelSpec(
            key="gte_multilingual_base",
            model_id="Alibaba-NLP/gte-multilingual-base",
            query_formatter=_identity,
            passage_formatter=_identity,
            normalize_embeddings=True,
            trust_remote_code=True,
        ),
        "bge_m3": EmbeddingModelSpec(
            key="bge_m3",
            model_id="BAAI/bge-m3",
            query_formatter=_identity,
            passage_formatter=_identity,
            normalize_embeddings=True,
        ),
        "multilingual_e5_large_instruct": EmbeddingModelSpec(
            key="multilingual_e5_large_instruct",
            model_id="intfloat/multilingual-e5-large-instruct",
            query_formatter=lambda text: f"{E5_INSTRUCTION}\nQuery: {text}",
            passage_formatter=_identity,
            normalize_embeddings=True,
        ),
        "turkish_e5_large": EmbeddingModelSpec(
            key="turkish_e5_large",
            model_id="ytu-ce-cosmos/turkish-e5-large",
            query_formatter=lambda text: (
                f"Instruct: {TURKISH_E5_INSTRUCTION}\nQuery: {text}"
            ),
            passage_formatter=_identity,
            normalize_embeddings=True,
        ),
    }


class EmbeddingAdapter(Protocol):
    spec: EmbeddingModelSpec
    is_official: bool

    def encode_queries(self, texts: list[str]) -> list[list[float]]: ...

    def encode_passages(self, texts: list[str]) -> list[list[float]]: ...

    def efficiency(self) -> dict[str, float | int]: ...

    def truncation_rate(self, texts: list[str]) -> float: ...

    def release(self) -> None: ...


class SentenceTransformerEmbeddingAdapter:
    """Evaluation adapter with per-model formatting, not a production provider."""

    is_official = True

    def __init__(self, spec: EmbeddingModelSpec) -> None:
        from sentence_transformers import SentenceTransformer

        self.spec = spec
        started = time.perf_counter()
        self._model = SentenceTransformer(
            spec.model_id,
            trust_remote_code=spec.trust_remote_code,
        )
        if spec.max_sequence_length is not None:
            self._model.max_seq_length = spec.max_sequence_length
        self._load_seconds = time.perf_counter() - started
        self._query_seconds = 0.0
        self._passage_seconds = 0.0
        self._query_count = 0
        self._passage_count = 0
        self._peak_cuda_memory = _peak_cuda_memory()

    def encode_queries(self, texts: list[str]) -> list[list[float]]:
        started = time.perf_counter()
        result = self._model.encode(
            [self.spec.query_formatter(text) for text in texts],
            normalize_embeddings=self.spec.normalize_embeddings,
        ).tolist()
        self._query_seconds += time.perf_counter() - started
        self._query_count += len(texts)
        self._peak_cuda_memory = max(self._peak_cuda_memory, _peak_cuda_memory())
        return result

    def encode_passages(self, texts: list[str]) -> list[list[float]]:
        started = time.perf_counter()
        result = self._model.encode(
            [self.spec.passage_formatter(text) for text in texts],
            normalize_embeddings=self.spec.normalize_embeddings,
        ).tolist()
        self._passage_seconds += time.perf_counter() - started
        self._passage_count += len(texts)
        self._peak_cuda_memory = max(self._peak_cuda_memory, _peak_cuda_memory())
        return result

    def efficiency(self) -> dict[str, float | int]:
        return {
            "embedding_dimension": self._model.get_sentence_embedding_dimension(),
            "model_load_seconds": self._load_seconds,
            "passage_embedding_seconds": self._passage_seconds,
            "query_embedding_seconds": self._query_seconds,
            "passages_per_second": _throughput(
                self._passage_count, self._passage_seconds
            ),
            "queries_per_second": _throughput(self._query_count, self._query_seconds),
            "peak_cuda_memory_bytes": self._peak_cuda_memory,
        }

    def truncation_rate(self, texts: list[str]) -> float:
        tokenizer = self._model.tokenizer
        limit = self._model.max_seq_length
        lengths = [
            len(
                tokenizer(self.spec.passage_formatter(text), truncation=False)[
                    "input_ids"
                ]
            )
            for text in texts
        ]
        return (
            sum(length > limit for length in lengths) / len(lengths) if lengths else 0.0
        )

    def release(self) -> None:
        del self._model
        gc.collect()
        try:
            import torch

            if torch.cuda.is_available():
                torch.cuda.empty_cache()
        except ImportError:
            pass


@dataclass(frozen=True)
class EmbeddingBenchmarkResult:
    model_key: str
    model_id: str
    is_official: bool
    metrics: dict[str, float]
    by_language: dict[str, dict[str, float]]
    by_category: dict[str, dict[str, float]]
    efficiency: dict[str, float | int]
    truncation_rate: float


def frozen_production_chunks(dataset: EvaluationDataset) -> tuple[EvaluationChunk, ...]:
    config = ChunkingConfig(target_tokens=350, max_tokens=500, overlap_tokens=40)
    return tuple(
        chunk
        for document in dataset.documents
        for chunk in production_structure_aware_chunks(document, config=config)
    )


def benchmark_embedding_model(
    dataset: EvaluationDataset,
    *,
    chunks: tuple[EvaluationChunk, ...],
    adapter: EmbeddingAdapter,
) -> EmbeddingBenchmarkResult:
    passage_embeddings = adapter.encode_passages([chunk.text for chunk in chunks])
    query_embeddings = adapter.encode_queries([query.text for query in dataset.queries])
    rankings = [
        _ranked_block_ids(query, chunks, passage_embeddings, query_embedding)
        for query, query_embedding in zip(
            dataset.queries, query_embeddings, strict=True
        )
    ]
    relevant_sets = [query.relevant_block_ids for query in dataset.queries]
    metrics = aggregate_rankings(rankings, relevant_sets)
    metrics["required_block_coverage_at_5"] = _mean_coverage(rankings, relevant_sets, 5)
    metrics["required_block_coverage_at_10"] = _mean_coverage(
        rankings, relevant_sets, 10
    )
    return EmbeddingBenchmarkResult(
        model_key=adapter.spec.key,
        model_id=adapter.spec.model_id,
        is_official=adapter.is_official,
        metrics=metrics,
        by_language=_group_metrics(
            dataset.queries, rankings, lambda query: query.language
        ),
        by_category=_group_metrics(
            dataset.queries, rankings, lambda query: query.category
        ),
        efficiency=adapter.efficiency(),
        truncation_rate=adapter.truncation_rate([chunk.text for chunk in chunks]),
    )


def save_embedding_results(
    results: list[EmbeddingBenchmarkResult],
    *,
    dataset_version: str,
    output_dir: Path,
    runtime_metadata: dict[str, str],
) -> None:
    if any(not result.is_official for result in results):
        raise ValueError("Debug embeddings must not write official benchmark results.")
    output_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "experimentVersion": "m4.2",
        "datasetVersion": dataset_version,
        "runtime": runtime_metadata,
        "chunkingConfiguration": {
            "target_tokens": 350,
            "max_tokens": 500,
            "overlap_tokens": 40,
        },
        "results": [asdict(result) for result in results],
        "timestamp": datetime.now(UTC).isoformat(),
    }
    (output_dir / "embedding_results_v1.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    fields = [
        "model",
        "recall_at_5",
        "recall_at_10",
        "mrr",
        "ndcg_at_10",
        "hit_rate_at_5",
        "required_block_coverage_at_5",
        "required_block_coverage_at_10",
        "embedding_dimension",
        "queries_per_second",
        "passages_per_second",
    ]
    with (output_dir / "embedding_results_v1.csv").open(
        "w", encoding="utf-8", newline=""
    ) as file:
        writer = csv.DictWriter(file, fieldnames=fields)
        writer.writeheader()
        for result in results:
            writer.writerow(
                {"model": result.model_id, **result.metrics, **result.efficiency}
            )


def _ranked_block_ids(
    query: EvaluationQuery,
    chunks: tuple[EvaluationChunk, ...],
    passage_embeddings: list[list[float]],
    query_embedding: list[float],
) -> list[frozenset[str]]:
    ranked = sorted(
        zip(chunks, passage_embeddings, strict=True),
        key=lambda item: _cosine(query_embedding, item[1]),
        reverse=True,
    )
    return [chunk.source_block_ids for chunk, _ in ranked]


def _group_metrics(
    queries: tuple[EvaluationQuery, ...],
    rankings: list[list[frozenset[str]]],
    key: Callable[[EvaluationQuery], str],
) -> dict[str, dict[str, float]]:
    grouped: dict[str, list[tuple[list[frozenset[str]], frozenset[str]]]] = {}
    for query, ranking in zip(queries, rankings, strict=True):
        grouped.setdefault(key(query), []).append((ranking, query.relevant_block_ids))
    return {
        name: _metrics_for_group(values) for name, values in sorted(grouped.items())
    }


def _metrics_for_group(
    values: list[tuple[list[frozenset[str]], frozenset[str]]],
) -> dict[str, float]:
    rankings = [ranking for ranking, _ in values]
    relevant = [blocks for _, blocks in values]
    metrics = aggregate_rankings(rankings, relevant)
    metrics["required_block_coverage_at_5"] = _mean_coverage(rankings, relevant, 5)
    metrics["required_block_coverage_at_10"] = _mean_coverage(rankings, relevant, 10)
    return metrics


def _mean_coverage(
    rankings: list[list[frozenset[str]]], required: list[frozenset[str]], k: int
) -> float:
    return (
        sum(
            required_block_coverage_at_k(ranking, blocks, k)
            for ranking, blocks in zip(rankings, required, strict=True)
        )
        / len(rankings)
        if rankings
        else 0.0
    )


def _cosine(left: list[float], right: list[float]) -> float:
    denominator = math.sqrt(sum(value * value for value in left)) * math.sqrt(
        sum(value * value for value in right)
    )
    return (
        sum(a * b for a, b in zip(left, right, strict=True)) / denominator
        if denominator
        else 0.0
    )


def _throughput(count: int, seconds: float) -> float:
    return count / seconds if seconds else 0.0


def _peak_cuda_memory() -> int:
    try:
        import torch

        return (
            int(torch.cuda.max_memory_allocated()) if torch.cuda.is_available() else 0
        )
    except ImportError:
        return 0


def _identity(text: str) -> str:
    return text
