"""M4.3 sparse and dense baseline evaluation over frozen production chunks."""

import csv
import json
import math
import re
import time
from collections import Counter
from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

from evals.src.chunking_eval import EvaluationChunk
from evals.src.dataset import EvaluationDataset, EvaluationQuery
from evals.src.embedding_eval import EmbeddingAdapter
from evals.src.metrics import aggregate_rankings, required_block_coverage_at_k

BM25_K1 = 1.5
BM25_B = 0.75
QUALITY_FIELDS = (
    "recall_at_5",
    "recall_at_10",
    "mrr",
    "ndcg_at_10",
    "hit_rate_at_5",
    "required_block_coverage_at_5",
    "required_block_coverage_at_10",
)
CSV_FIELDNAMES = (
    "retriever_key",
    "retriever",
    *QUALITY_FIELDS,
    "index_build_seconds",
    "query_embedding_seconds",
    "query_retrieval_seconds",
    "chunk_count",
    "bm25_k1",
    "bm25_b",
)


@dataclass(frozen=True)
class RetrievalBenchmarkResult:
    retriever_key: str
    retriever: str
    metrics: dict[str, float]
    by_language: dict[str, dict[str, float]]
    by_category: dict[str, dict[str, float]]
    efficiency: dict[str, float | int]
    parameters: dict[str, float | str]


class Bm25Retriever:
    """Deterministic in-memory BM25 baseline; evaluation-only, not production RAG."""

    def __init__(self, documents: list[str], *, k1: float = BM25_K1, b: float = BM25_B):
        if k1 <= 0 or not 0 <= b <= 1:
            raise ValueError("BM25 requires k1 > 0 and b between 0 and 1.")
        self.k1 = k1
        self.b = b
        self._documents = [tokenize_lexical(document) for document in documents]
        self._lengths = [len(document) for document in self._documents]
        self._average_length = (
            sum(self._lengths) / len(self._lengths) if self._lengths else 0.0
        )
        self._document_frequencies = Counter(
            token for document in self._documents for token in set(document)
        )
        self._term_frequencies = [Counter(document) for document in self._documents]

    def rank(self, query: str) -> list[int]:
        query_tokens = set(tokenize_lexical(query))
        scores = [
            self._score(query_tokens, index) for index in range(len(self._documents))
        ]
        return sorted(range(len(scores)), key=lambda index: (-scores[index], index))

    def _score(self, query_tokens: set[str], index: int) -> float:
        if not self._average_length:
            return 0.0
        term_frequencies = self._term_frequencies[index]
        length_normalizer = (
            1 - self.b + self.b * self._lengths[index] / self._average_length
        )
        return sum(
            self._inverse_document_frequency(token)
            * term_frequencies[token]
            * (self.k1 + 1)
            / (term_frequencies[token] + self.k1 * length_normalizer)
            for token in query_tokens
            if term_frequencies[token]
        )

    def _inverse_document_frequency(self, token: str) -> float:
        document_count = len(self._documents)
        frequency = self._document_frequencies[token]
        return math.log(1 + (document_count - frequency + 0.5) / (frequency + 0.5))


def tokenize_lexical(text: str) -> list[str]:
    """Unicode-aware, locale-independent lexical tokens for Turkish and English."""
    normalized = text.casefold().replace("\u0307", "")
    return re.findall(r"[^\W_]+", normalized, flags=re.UNICODE)


def run_dense_baseline(
    dataset: EvaluationDataset,
    *,
    chunks: tuple[EvaluationChunk, ...],
    adapter: EmbeddingAdapter,
) -> RetrievalBenchmarkResult:
    passage_embeddings = adapter.encode_passages([chunk.text for chunk in chunks])
    started = time.perf_counter()
    query_embeddings = adapter.encode_queries([query.text for query in dataset.queries])
    query_embedding_seconds = time.perf_counter() - started
    started = time.perf_counter()
    rankings = [
        _dense_ranking(chunks, passage_embeddings, query_embedding)
        for query_embedding in query_embeddings
    ]
    query_retrieval_seconds = time.perf_counter() - started
    return _build_result(
        retriever_key="dense_e5",
        retriever="Dense — intfloat/multilingual-e5-large-instruct",
        dataset=dataset,
        rankings=rankings,
        efficiency={
            "query_embedding_seconds": query_embedding_seconds,
            "query_retrieval_seconds": query_retrieval_seconds,
            "chunk_count": len(chunks),
        },
        parameters={"model_id": adapter.spec.model_id},
    )


def run_bm25_baseline(
    dataset: EvaluationDataset,
    *,
    chunks: tuple[EvaluationChunk, ...],
    k1: float = BM25_K1,
    b: float = BM25_B,
) -> RetrievalBenchmarkResult:
    started = time.perf_counter()
    retriever = Bm25Retriever([chunk.text for chunk in chunks], k1=k1, b=b)
    index_build_seconds = time.perf_counter() - started
    started = time.perf_counter()
    rankings = [
        [chunks[index].source_block_ids for index in retriever.rank(query.text)]
        for query in dataset.queries
    ]
    query_retrieval_seconds = time.perf_counter() - started
    return _build_result(
        retriever_key="sparse_bm25",
        retriever="Sparse — BM25",
        dataset=dataset,
        rankings=rankings,
        efficiency={
            "index_build_seconds": index_build_seconds,
            "query_retrieval_seconds": query_retrieval_seconds,
            "chunk_count": len(chunks),
        },
        parameters={"bm25_k1": k1, "bm25_b": b, "tokenizer": "unicode_casefold"},
    )


def save_retrieval_results(
    results: list[RetrievalBenchmarkResult],
    *,
    dataset_version: str,
    output_dir: Path,
    runtime_metadata: dict[str, str],
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    rows = [_csv_row(result) for result in results]
    payload = {
        "experimentVersion": "m4.3",
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
    (output_dir / "sparse_dense_results_v1.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    with (output_dir / "sparse_dense_results_v1.csv").open(
        "w", encoding="utf-8", newline=""
    ) as file:
        writer = csv.DictWriter(file, fieldnames=CSV_FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)


def _build_result(
    *,
    retriever_key: str,
    retriever: str,
    dataset: EvaluationDataset,
    rankings: list[list[frozenset[str]]],
    efficiency: dict[str, float | int],
    parameters: dict[str, float | str],
) -> RetrievalBenchmarkResult:
    relevant_sets = [query.relevant_block_ids for query in dataset.queries]
    return RetrievalBenchmarkResult(
        retriever_key=retriever_key,
        retriever=retriever,
        metrics=_metrics(rankings, relevant_sets),
        by_language=_group_metrics(
            dataset.queries, rankings, lambda query: query.language
        ),
        by_category=_group_metrics(
            dataset.queries, rankings, lambda query: query.category
        ),
        efficiency=efficiency,
        parameters=parameters,
    )


def _metrics(
    rankings: list[list[frozenset[str]]],
    relevant_sets: list[frozenset[str]],
) -> dict[str, float]:
    metrics = aggregate_rankings(rankings, relevant_sets)
    metrics["required_block_coverage_at_5"] = _mean_coverage(rankings, relevant_sets, 5)
    metrics["required_block_coverage_at_10"] = _mean_coverage(
        rankings, relevant_sets, 10
    )
    return metrics


def _group_metrics(
    queries: tuple[EvaluationQuery, ...],
    rankings: list[list[frozenset[str]]],
    key: Callable[[EvaluationQuery], str],
) -> dict[str, dict[str, float]]:
    groups: dict[str, list[tuple[list[frozenset[str]], frozenset[str]]]] = {}
    for query, ranking in zip(queries, rankings, strict=True):
        groups.setdefault(key(query), []).append((ranking, query.relevant_block_ids))
    return {
        name: _metrics(
            [ranking for ranking, _ in values],
            [relevant for _, relevant in values],
        )
        for name, values in sorted(groups.items())
    }


def _mean_coverage(
    rankings: list[list[frozenset[str]]],
    relevant_sets: list[frozenset[str]],
    k: int,
) -> float:
    return (
        sum(
            required_block_coverage_at_k(ranking, relevant, k)
            for ranking, relevant in zip(rankings, relevant_sets, strict=True)
        )
        / len(rankings)
        if rankings
        else 0.0
    )


def _dense_ranking(
    chunks: tuple[EvaluationChunk, ...],
    passage_embeddings: list[list[float]],
    query_embedding: list[float],
) -> list[frozenset[str]]:
    scored = sorted(
        zip(chunks, passage_embeddings, strict=True),
        key=lambda item: (-_cosine(query_embedding, item[1]), item[0].chunk_index),
    )
    return [chunk.source_block_ids for chunk, _ in scored]


def _cosine(left: list[float], right: list[float]) -> float:
    denominator = math.sqrt(sum(value * value for value in left)) * math.sqrt(
        sum(value * value for value in right)
    )
    return (
        sum(a * b for a, b in zip(left, right, strict=True)) / denominator
        if denominator
        else 0.0
    )


def _csv_row(result: RetrievalBenchmarkResult) -> dict[str, str | float | int | None]:
    unexpected_metrics = set(result.metrics) - set(QUALITY_FIELDS)
    unexpected_efficiency = set(result.efficiency) - {
        "index_build_seconds",
        "query_embedding_seconds",
        "query_retrieval_seconds",
        "chunk_count",
    }
    unexpected_parameters = set(result.parameters) - {
        "bm25_k1",
        "bm25_b",
        "model_id",
        "tokenizer",
    }
    if unexpected_metrics or unexpected_efficiency or unexpected_parameters:
        fields = sorted(
            unexpected_metrics | unexpected_efficiency | unexpected_parameters
        )
        raise ValueError(f"Result fields are missing from the CSV schema: {fields}")
    return {
        "retriever_key": result.retriever_key,
        "retriever": result.retriever,
        **{field: result.metrics.get(field) for field in QUALITY_FIELDS},
        "index_build_seconds": result.efficiency.get("index_build_seconds"),
        "query_embedding_seconds": result.efficiency.get("query_embedding_seconds"),
        "query_retrieval_seconds": result.efficiency.get("query_retrieval_seconds"),
        "chunk_count": result.efficiency.get("chunk_count"),
        "bm25_k1": result.parameters.get("bm25_k1"),
        "bm25_b": result.parameters.get("bm25_b"),
    }
