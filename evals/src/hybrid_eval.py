"""M4.4 evaluation-only dense, BM25, and Reciprocal Rank Fusion comparison."""

import csv
import json
import time
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

from evals.src.chunking_eval import EvaluationChunk
from evals.src.dataset import EvaluationDataset
from evals.src.embedding_eval import EmbeddingAdapter
from evals.src.retrieval_eval import (
    BM25_B,
    BM25_K1,
    QUALITY_FIELDS,
    RetrievalBenchmarkResult,
    block_rankings,
    bm25_ranked_indices,
    build_retrieval_result,
    dense_ranked_indices,
)

RRF_K = 60
CANDIDATE_DEPTH = 20
CSV_FIELDNAMES = (
    "retriever_key",
    "retriever",
    *QUALITY_FIELDS,
    "candidate_depth",
    "rrf_k",
    "dense_query_embedding_seconds",
    "dense_query_retrieval_seconds",
    "sparse_index_build_seconds",
    "sparse_query_retrieval_seconds",
    "fusion_seconds",
    "chunk_count",
    "bm25_k1",
    "bm25_b",
)


@dataclass(frozen=True)
class HybridEvaluation:
    results: tuple[RetrievalBenchmarkResult, ...]
    diagnostics: dict[str, list[str]]


def reciprocal_rank_fusion(
    dense_ranking: list[int],
    sparse_ranking: list[int],
    *,
    k: int = RRF_K,
    candidate_depth: int = CANDIDATE_DEPTH,
) -> list[int]:
    """Fuse rank positions only; ties use best rank, then stable chunk index."""
    if k <= 0 or candidate_depth <= 0:
        raise ValueError("RRF requires positive k and candidate depth.")
    scores: dict[int, float] = {}
    best_ranks: dict[int, int] = {}
    for ranking in (dense_ranking[:candidate_depth], sparse_ranking[:candidate_depth]):
        seen: set[int] = set()
        for rank, candidate in enumerate(ranking, start=1):
            if candidate in seen:
                continue
            seen.add(candidate)
            scores[candidate] = scores.get(candidate, 0.0) + 1 / (k + rank)
            best_ranks[candidate] = min(best_ranks.get(candidate, rank), rank)
    return sorted(
        scores,
        key=lambda candidate: (-scores[candidate], best_ranks[candidate], candidate),
    )


def run_hybrid_benchmark(
    dataset: EvaluationDataset,
    *,
    chunks: tuple[EvaluationChunk, ...],
    adapter: EmbeddingAdapter,
    rrf_k: int = RRF_K,
    candidate_depth: int = CANDIDATE_DEPTH,
) -> HybridEvaluation:
    dense_indices, dense_efficiency = dense_ranked_indices(
        dataset, chunks=chunks, adapter=adapter, candidate_depth=candidate_depth
    )
    sparse_indices, sparse_efficiency = bm25_ranked_indices(
        dataset,
        chunks=chunks,
        k1=BM25_K1,
        b=BM25_B,
        candidate_depth=candidate_depth,
    )
    started = time.perf_counter()
    hybrid_indices = [
        reciprocal_rank_fusion(
            dense_ranking,
            sparse_ranking,
            k=rrf_k,
            candidate_depth=candidate_depth,
        )
        for dense_ranking, sparse_ranking in zip(
            dense_indices, sparse_indices, strict=True
        )
    ]
    fusion_seconds = time.perf_counter() - started
    dense_rankings = block_rankings(chunks, dense_indices)
    sparse_rankings = block_rankings(chunks, sparse_indices)
    hybrid_rankings = block_rankings(chunks, hybrid_indices)
    dense_result = build_retrieval_result(
        retriever_key="dense_e5",
        retriever="Dense — intfloat/multilingual-e5-large-instruct",
        dataset=dataset,
        rankings=dense_rankings,
        efficiency=dense_efficiency,
        parameters={
            "model_id": adapter.spec.model_id,
            "candidate_depth": candidate_depth,
        },
    )
    sparse_result = build_retrieval_result(
        retriever_key="sparse_bm25",
        retriever="Sparse — BM25",
        dataset=dataset,
        rankings=sparse_rankings,
        efficiency=sparse_efficiency,
        parameters={
            "bm25_k1": BM25_K1,
            "bm25_b": BM25_B,
            "candidate_depth": candidate_depth,
        },
    )
    hybrid_result = build_retrieval_result(
        retriever_key="hybrid_rrf",
        retriever="Hybrid — Dense + BM25 RRF",
        dataset=dataset,
        rankings=hybrid_rankings,
        efficiency={
            "dense_query_embedding_seconds": dense_efficiency[
                "query_embedding_seconds"
            ],
            "dense_query_retrieval_seconds": dense_efficiency[
                "query_retrieval_seconds"
            ],
            "sparse_index_build_seconds": sparse_efficiency["index_build_seconds"],
            "sparse_query_retrieval_seconds": sparse_efficiency[
                "query_retrieval_seconds"
            ],
            "fusion_seconds": fusion_seconds,
            "chunk_count": len(chunks),
        },
        parameters={
            "rrf_k": rrf_k,
            "candidate_depth": candidate_depth,
            "bm25_k1": BM25_K1,
            "bm25_b": BM25_B,
            "dense_model_id": adapter.spec.model_id,
        },
    )
    return HybridEvaluation(
        results=(dense_result, sparse_result, hybrid_result),
        diagnostics=_diagnostics(
            dataset, dense_rankings, sparse_rankings, hybrid_rankings
        ),
    )


def save_hybrid_results(
    evaluation: HybridEvaluation,
    *,
    dataset_version: str,
    output_dir: Path,
    runtime_metadata: dict[str, str],
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    rows = [_csv_row(result) for result in evaluation.results]
    payload = {
        "experimentVersion": "m4.4",
        "datasetVersion": dataset_version,
        "runtime": runtime_metadata,
        "chunkingConfiguration": {
            "target_tokens": 350,
            "max_tokens": 500,
            "overlap_tokens": 40,
        },
        "results": [asdict(result) for result in evaluation.results],
        "diagnostics": evaluation.diagnostics,
        "timestamp": datetime.now(UTC).isoformat(),
    }
    (output_dir / "hybrid_rrf_results_v1.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    with (output_dir / "hybrid_rrf_results_v1.csv").open(
        "w", encoding="utf-8", newline=""
    ) as file:
        writer = csv.DictWriter(file, fieldnames=CSV_FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)


def _diagnostics(
    dataset: EvaluationDataset,
    dense_rankings: list[list[frozenset[str]]],
    sparse_rankings: list[list[frozenset[str]]],
    hybrid_rankings: list[list[frozenset[str]]],
) -> dict[str, list[str]]:
    diagnostics = {
        "hybrid_improves_dense": [],
        "hybrid_hurts_dense": [],
        "hybrid_recovers_dense_miss": [],
        "bm25_only_signal": [],
        "dense_only_signal": [],
    }
    for query, dense, sparse, hybrid in zip(
        dataset.queries, dense_rankings, sparse_rankings, hybrid_rankings, strict=True
    ):
        dense_rank = _first_relevant_rank(dense, query.relevant_block_ids)
        sparse_rank = _first_relevant_rank(sparse, query.relevant_block_ids)
        hybrid_rank = _first_relevant_rank(hybrid, query.relevant_block_ids)
        if hybrid_rank is not None and (dense_rank is None or hybrid_rank < dense_rank):
            diagnostics["hybrid_improves_dense"].append(query.id)
        if dense_rank is not None and (hybrid_rank is None or hybrid_rank > dense_rank):
            diagnostics["hybrid_hurts_dense"].append(query.id)
        if dense_rank is None and hybrid_rank is not None:
            diagnostics["hybrid_recovers_dense_miss"].append(query.id)
        if sparse_rank is not None and dense_rank is None and hybrid_rank is not None:
            diagnostics["bm25_only_signal"].append(query.id)
        if dense_rank is not None and sparse_rank is None and hybrid_rank is not None:
            diagnostics["dense_only_signal"].append(query.id)
    return diagnostics


def _first_relevant_rank(
    ranking: list[frozenset[str]], relevant_block_ids: frozenset[str]
) -> int | None:
    for index, block_ids in enumerate(ranking[:10], start=1):
        if block_ids & relevant_block_ids:
            return index
    return None


def _csv_row(result: RetrievalBenchmarkResult) -> dict[str, str | float | int | None]:
    return {
        "retriever_key": result.retriever_key,
        "retriever": result.retriever,
        **{field: result.metrics.get(field) for field in QUALITY_FIELDS},
        "candidate_depth": result.parameters.get("candidate_depth"),
        "rrf_k": result.parameters.get("rrf_k"),
        "dense_query_embedding_seconds": result.efficiency.get(
            "dense_query_embedding_seconds",
            result.efficiency.get("query_embedding_seconds"),
        ),
        "dense_query_retrieval_seconds": result.efficiency.get(
            "dense_query_retrieval_seconds",
            result.efficiency.get("query_retrieval_seconds"),
        ),
        "sparse_index_build_seconds": result.efficiency.get(
            "sparse_index_build_seconds", result.efficiency.get("index_build_seconds")
        ),
        "sparse_query_retrieval_seconds": result.efficiency.get(
            "sparse_query_retrieval_seconds",
            result.efficiency.get("query_retrieval_seconds"),
        ),
        "fusion_seconds": result.efficiency.get("fusion_seconds"),
        "chunk_count": result.efficiency.get("chunk_count"),
        "bm25_k1": result.parameters.get("bm25_k1"),
        "bm25_b": result.parameters.get("bm25_b"),
    }
