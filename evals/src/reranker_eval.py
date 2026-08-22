"""M4.5 evaluation-only multilingual reranker benchmark."""

import csv
import gc
import json
import time
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol

from evals.src.chunking_eval import EvaluationChunk
from evals.src.dataset import EvaluationDataset
from evals.src.embedding_eval import EmbeddingAdapter
from evals.src.hybrid_eval import CANDIDATE_DEPTH, RRF_K, reciprocal_rank_fusion
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

RERANKER_MODEL_ID = "BAAI/bge-reranker-v2-m3"
CSV_FIELDNAMES = (
    "retriever_key",
    "retriever",
    *QUALITY_FIELDS,
    "candidate_depth",
    "reranker_model_id",
    "model_load_seconds",
    "total_reranking_seconds",
    "pairs_scored",
    "pairs_per_second",
    "peak_cuda_memory_bytes",
)


class RerankerAdapter(Protocol):
    model_id: str

    def score(self, query: str, passages: list[str]) -> list[float]: ...

    def efficiency(self) -> dict[str, float | int]: ...

    def release(self) -> None: ...


class CrossEncoderReranker:
    """Evaluation-only BGE cross-encoder adapter; scores query/passage pairs."""

    model_id = RERANKER_MODEL_ID

    def __init__(self, model_id: str = RERANKER_MODEL_ID) -> None:
        from sentence_transformers import CrossEncoder

        self.model_id = model_id
        started = time.perf_counter()
        self._model = CrossEncoder(model_id)
        self._model_load_seconds = time.perf_counter() - started
        self._reranking_seconds = 0.0
        self._pair_count = 0
        self._peak_cuda_memory = _peak_cuda_memory()

    def score(self, query: str, passages: list[str]) -> list[float]:
        started = time.perf_counter()
        scores = self._model.predict([(query, passage) for passage in passages])
        self._reranking_seconds += time.perf_counter() - started
        self._pair_count += len(passages)
        self._peak_cuda_memory = max(self._peak_cuda_memory, _peak_cuda_memory())
        return [float(score) for score in scores]

    def efficiency(self) -> dict[str, float | int]:
        return {
            "model_load_seconds": self._model_load_seconds,
            "total_reranking_seconds": self._reranking_seconds,
            "pairs_scored": self._pair_count,
            "pairs_per_second": _throughput(self._pair_count, self._reranking_seconds),
            "peak_cuda_memory_bytes": self._peak_cuda_memory,
        }

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
class RerankerEvaluation:
    results: tuple[RetrievalBenchmarkResult, ...]
    diagnostics: dict[str, list[str]]


def rerank_candidates(
    query: str,
    candidate_indices: list[int],
    *,
    chunks: tuple[EvaluationChunk, ...],
    reranker: RerankerAdapter,
) -> list[int]:
    scores = reranker.score(query, [chunks[index].text for index in candidate_indices])
    if len(scores) != len(candidate_indices):
        raise ValueError("Reranker score count must match the candidate count.")
    scored = sorted(
        enumerate(zip(candidate_indices, scores, strict=True)),
        key=lambda item: (-item[1][1], item[0], item[1][0]),
    )
    return [candidate for _, (candidate, _) in scored]


def run_reranker_benchmark(
    dataset: EvaluationDataset,
    *,
    chunks: tuple[EvaluationChunk, ...],
    adapter: EmbeddingAdapter,
    reranker: RerankerAdapter,
    candidate_depth: int = CANDIDATE_DEPTH,
) -> RerankerEvaluation:
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
    hybrid_indices = [
        reciprocal_rank_fusion(
            dense_ranking,
            sparse_ranking,
            k=RRF_K,
            candidate_depth=candidate_depth,
        )[:candidate_depth]
        for dense_ranking, sparse_ranking in zip(
            dense_indices, sparse_indices, strict=True
        )
    ]
    dense_reranked_indices = [
        rerank_candidates(query.text, candidates, chunks=chunks, reranker=reranker)
        for query, candidates in zip(dataset.queries, dense_indices, strict=True)
    ]
    hybrid_reranked_indices = [
        rerank_candidates(query.text, candidates, chunks=chunks, reranker=reranker)
        for query, candidates in zip(dataset.queries, hybrid_indices, strict=True)
    ]
    dense_rankings = block_rankings(chunks, dense_indices)
    hybrid_rankings = block_rankings(chunks, hybrid_indices)
    dense_reranked_rankings = block_rankings(chunks, dense_reranked_indices)
    hybrid_reranked_rankings = block_rankings(chunks, hybrid_reranked_indices)
    reranker_efficiency = reranker.efficiency()
    shared_parameters = {"candidate_depth": candidate_depth, "rrf_k": RRF_K}
    dense_result = build_retrieval_result(
        retriever_key="dense_e5",
        retriever="Dense — intfloat/multilingual-e5-large-instruct",
        dataset=dataset,
        rankings=dense_rankings,
        efficiency=dense_efficiency,
        parameters={"model_id": adapter.spec.model_id, **shared_parameters},
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
            "chunk_count": len(chunks),
        },
        parameters={"bm25_k1": BM25_K1, "bm25_b": BM25_B, **shared_parameters},
    )
    dense_reranked_result = build_retrieval_result(
        retriever_key="dense_reranker",
        retriever="Dense + Reranker",
        dataset=dataset,
        rankings=dense_reranked_rankings,
        efficiency=reranker_efficiency,
        parameters={"reranker_model_id": reranker.model_id, **shared_parameters},
    )
    hybrid_reranked_result = build_retrieval_result(
        retriever_key="hybrid_reranker",
        retriever="Hybrid RRF + Reranker",
        dataset=dataset,
        rankings=hybrid_reranked_rankings,
        efficiency=reranker_efficiency,
        parameters={"reranker_model_id": reranker.model_id, **shared_parameters},
    )
    return RerankerEvaluation(
        results=(
            dense_result,
            hybrid_result,
            dense_reranked_result,
            hybrid_reranked_result,
        ),
        diagnostics=_diagnostics(
            dataset,
            dense_rankings,
            hybrid_rankings,
            dense_reranked_rankings,
            hybrid_reranked_rankings,
        ),
    )


def save_reranker_results(
    evaluation: RerankerEvaluation,
    *,
    dataset_version: str,
    output_dir: Path,
    runtime_metadata: dict[str, str],
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "experimentVersion": "m4.5",
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
    (output_dir / "reranker_results_v1.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    with (output_dir / "reranker_results_v1.csv").open(
        "w", encoding="utf-8", newline=""
    ) as file:
        writer = csv.DictWriter(file, fieldnames=CSV_FIELDNAMES)
        writer.writeheader()
        writer.writerows(_csv_row(result) for result in evaluation.results)


def _diagnostics(
    dataset: EvaluationDataset,
    dense_rankings: list[list[frozenset[str]]],
    hybrid_rankings: list[list[frozenset[str]]],
    dense_reranked_rankings: list[list[frozenset[str]]],
    hybrid_reranked_rankings: list[list[frozenset[str]]],
) -> dict[str, list[str]]:
    diagnostics = {
        "dense_reranker_improves": [],
        "dense_reranker_hurts": [],
        "dense_rescued_into_top_5": [],
        "hybrid_reranker_improves": [],
        "hybrid_reranker_hurts": [],
        "hybrid_rescued_into_top_5": [],
        "hybrid_pool_helps_reranker": [],
        "dense_pool_sufficient_or_better": [],
    }
    for query, dense, hybrid, dense_reranked, hybrid_reranked in zip(
        dataset.queries,
        dense_rankings,
        hybrid_rankings,
        dense_reranked_rankings,
        hybrid_reranked_rankings,
        strict=True,
    ):
        dense_rank = _first_relevant_rank(dense, query.relevant_block_ids, 10)
        hybrid_rank = _first_relevant_rank(hybrid, query.relevant_block_ids, 10)
        dense_reranked_rank = _first_relevant_rank(
            dense_reranked, query.relevant_block_ids, 10
        )
        hybrid_reranked_rank = _first_relevant_rank(
            hybrid_reranked, query.relevant_block_ids, 10
        )
        if _improved(dense_reranked_rank, dense_rank):
            diagnostics["dense_reranker_improves"].append(query.id)
        if _improved(dense_rank, dense_reranked_rank):
            diagnostics["dense_reranker_hurts"].append(query.id)
        if _rescued_into_top_5(dense_rank, dense_reranked_rank):
            diagnostics["dense_rescued_into_top_5"].append(query.id)
        if _improved(hybrid_reranked_rank, hybrid_rank):
            diagnostics["hybrid_reranker_improves"].append(query.id)
        if _improved(hybrid_rank, hybrid_reranked_rank):
            diagnostics["hybrid_reranker_hurts"].append(query.id)
        if _rescued_into_top_5(hybrid_rank, hybrid_reranked_rank):
            diagnostics["hybrid_rescued_into_top_5"].append(query.id)
        if _improved(hybrid_reranked_rank, dense_reranked_rank):
            diagnostics["hybrid_pool_helps_reranker"].append(query.id)
        if _improved(dense_reranked_rank, hybrid_reranked_rank):
            diagnostics["dense_pool_sufficient_or_better"].append(query.id)
    return diagnostics


def _first_relevant_rank(
    ranking: list[frozenset[str]], relevant_block_ids: frozenset[str], depth: int
) -> int | None:
    for index, block_ids in enumerate(ranking[:depth], start=1):
        if block_ids & relevant_block_ids:
            return index
    return None


def _improved(new_rank: int | None, previous_rank: int | None) -> bool:
    return new_rank is not None and (previous_rank is None or new_rank < previous_rank)


def _rescued_into_top_5(previous_rank: int | None, new_rank: int | None) -> bool:
    return (
        new_rank is not None
        and new_rank <= 5
        and (previous_rank is None or previous_rank > 5)
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


def _csv_row(result: RetrievalBenchmarkResult) -> dict[str, str | float | int | None]:
    return {
        "retriever_key": result.retriever_key,
        "retriever": result.retriever,
        **{field: result.metrics.get(field) for field in QUALITY_FIELDS},
        "candidate_depth": result.parameters.get("candidate_depth"),
        "reranker_model_id": result.parameters.get("reranker_model_id"),
        "model_load_seconds": result.efficiency.get("model_load_seconds"),
        "total_reranking_seconds": result.efficiency.get("total_reranking_seconds"),
        "pairs_scored": result.efficiency.get("pairs_scored"),
        "pairs_per_second": result.efficiency.get("pairs_per_second"),
        "peak_cuda_memory_bytes": result.efficiency.get("peak_cuda_memory_bytes"),
    }
