import ast
import csv
import json
from pathlib import Path

import pytest

from evals.src.dataset import (
    EvaluationBlock,
    EvaluationDataset,
    EvaluationDocument,
    EvaluationQuery,
)
from evals.src.embedding_eval import EmbeddingModelSpec, frozen_production_chunks
from evals.src.hybrid_eval import (
    CANDIDATE_DEPTH,
    RRF_K,
    HybridEvaluation,
    reciprocal_rank_fusion,
    run_hybrid_benchmark,
    save_hybrid_results,
)
from evals.src.retrieval_eval import RetrievalBenchmarkResult

ROOT = Path(__file__).resolve().parents[2]


class FakeDenseAdapter:
    is_official = True

    def __init__(self) -> None:
        self.spec = EmbeddingModelSpec(
            key="fake-dense",
            model_id="fake/dense",
            query_formatter=lambda text: text,
            passage_formatter=lambda text: text,
            normalize_embeddings=True,
        )
        self.passage_texts: list[str] = []

    def encode_queries(self, texts: list[str]) -> list[list[float]]:
        return [[1.0, 0.0] if "alpha" in text else [0.0, 1.0] for text in texts]

    def encode_passages(self, texts: list[str]) -> list[list[float]]:
        self.passage_texts = texts
        return [[1.0, 0.0] if "alpha" in text else [0.0, 1.0] for text in texts]

    def efficiency(self) -> dict[str, float | int]:
        return {}

    def truncation_rate(self, texts: list[str]) -> float:
        return 0.0

    def release(self) -> None:
        pass


def _dataset() -> EvaluationDataset:
    english = EvaluationDocument(
        "en-doc",
        "en",
        (
            EvaluationBlock("en-b0", "Alpha evidence", "paragraph", 0),
            EvaluationBlock("en-b1", "Beta evidence", "paragraph", 1),
        ),
    )
    turkish = EvaluationDocument(
        "tr-doc",
        "tr",
        (EvaluationBlock("tr-b0", "Beta kanıt", "paragraph", 0),),
    )
    return EvaluationDataset(
        "v1",
        (english, turkish),
        (
            EvaluationQuery(
                "q-en", "en-doc", "en", "alpha", frozenset({"en-b0"}), "factual"
            ),
            EvaluationQuery(
                "q-tr",
                "tr-doc",
                "tr",
                "beta",
                frozenset({"tr-b0"}),
                "morphology_heavy",
            ),
        ),
    )


def test_rrf_sums_rank_positions_for_overlapping_candidates() -> None:
    assert reciprocal_rank_fusion([0, 1], [1, 2], k=60) == [1, 0, 2]


def test_rrf_keeps_one_source_only_candidates_and_breaks_ties_by_chunk_index() -> None:
    assert reciprocal_rank_fusion([2], [1], k=60) == [1, 2]


def test_rrf_respects_candidate_depth_and_k_parameter() -> None:
    assert reciprocal_rank_fusion([2, 1, 0], [1, 3, 4], k=20, candidate_depth=2) == [
        1,
        2,
        3,
    ]
    assert reciprocal_rank_fusion([0], [1], k=RRF_K) == [0, 1]
    with pytest.raises(ValueError):
        reciprocal_rank_fusion([0], [1], k=0)


def test_hybrid_uses_shared_frozen_chunks_and_reports_language_category_metrics() -> (
    None
):
    dataset = _dataset()
    chunks = frozen_production_chunks(dataset)
    adapter = FakeDenseAdapter()
    evaluation = run_hybrid_benchmark(
        dataset,
        chunks=chunks,
        adapter=adapter,
        rrf_k=20,
        candidate_depth=CANDIDATE_DEPTH,
    )

    dense, sparse, hybrid = evaluation.results
    assert adapter.passage_texts == [chunk.text for chunk in chunks]
    assert [result.efficiency["chunk_count"] for result in evaluation.results] == [
        len(chunks),
        len(chunks),
        len(chunks),
    ]
    assert set(hybrid.by_language) == {"en", "tr"}
    assert set(hybrid.by_category) == {"factual", "morphology_heavy"}
    assert dense.parameters["candidate_depth"] == CANDIDATE_DEPTH
    assert sparse.parameters["bm25_k1"] == 1.5
    assert hybrid.parameters["rrf_k"] == 20


def test_hybrid_result_serialization_is_machine_readable(tmp_path) -> None:
    evaluation = HybridEvaluation(
        results=(
            RetrievalBenchmarkResult("dense_e5", "Dense", {"mrr": 1.0}, {}, {}, {}, {}),
            RetrievalBenchmarkResult(
                "sparse_bm25", "BM25", {"mrr": 0.5}, {}, {}, {}, {}
            ),
            RetrievalBenchmarkResult(
                "hybrid_rrf",
                "Hybrid",
                {"mrr": 0.75},
                {},
                {},
                {"fusion_seconds": 0.01, "chunk_count": 3},
                {"rrf_k": RRF_K, "candidate_depth": CANDIDATE_DEPTH},
            ),
        ),
        diagnostics={"hybrid_improves_dense": ["q1"]},
    )
    save_hybrid_results(
        evaluation, dataset_version="v1", output_dir=tmp_path, runtime_metadata={}
    )

    payload = json.loads((tmp_path / "hybrid_rrf_results_v1.json").read_text())
    with (tmp_path / "hybrid_rrf_results_v1.csv").open(newline="") as file:
        rows = list(csv.DictReader(file))

    assert [result["retriever_key"] for result in payload["results"]] == [
        "dense_e5",
        "sparse_bm25",
        "hybrid_rrf",
    ]
    assert payload["diagnostics"]["hybrid_improves_dense"] == ["q1"]
    assert len(rows) == 3
    assert rows[2]["rrf_k"] == "60"


def test_hybrid_notebook_is_valid_and_uses_primary_rrf_configuration() -> None:
    notebook = json.loads((ROOT / "notebooks/04_hybrid_rrf.ipynb").read_text())
    code = [
        "".join(cell["source"])
        for cell in notebook["cells"]
        if cell["cell_type"] == "code"
    ]
    for cell in code:
        ast.parse(cell)
    assert "transformers==4.57.6" in code[0]
    assert "frozen_production_chunks(dataset)" in code[1]
    assert "rrf_k=RRF_K, candidate_depth=CANDIDATE_DEPTH" in code[1]
