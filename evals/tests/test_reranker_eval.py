import csv
import json

from evals.src.dataset import (
    EvaluationBlock,
    EvaluationDataset,
    EvaluationDocument,
    EvaluationQuery,
)
from evals.src.embedding_eval import EmbeddingModelSpec, frozen_production_chunks
from evals.src.reranker_eval import (
    CANDIDATE_DEPTH,
    RERANKER_MODEL_ID,
    RerankerEvaluation,
    rerank_candidates,
    run_reranker_benchmark,
    save_reranker_results,
)
from evals.src.retrieval_eval import RetrievalBenchmarkResult


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

    def encode_queries(self, texts: list[str]) -> list[list[float]]:
        return [[1.0, 0.0] if "alpha" in text else [0.0, 1.0] for text in texts]

    def encode_passages(self, texts: list[str]) -> list[list[float]]:
        return [[1.0, 0.0] if "alpha" in text else [0.0, 1.0] for text in texts]

    def efficiency(self) -> dict[str, float | int]:
        return {}

    def truncation_rate(self, texts: list[str]) -> float:
        return 0.0

    def release(self) -> None:
        pass


class FakeReranker:
    model_id = "fake/reranker"

    def __init__(self, scores: list[float] | None = None) -> None:
        self._scores = scores
        self.calls: list[tuple[str, list[str]]] = []

    def score(self, query: str, passages: list[str]) -> list[float]:
        self.calls.append((query, passages))
        if self._scores is not None:
            return self._scores[: len(passages)]
        return [float(index) for index in range(len(passages))]

    def efficiency(self) -> dict[str, float | int]:
        return {"pairs_scored": sum(len(passages) for _, passages in self.calls)}

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


def test_reranker_orders_by_scores_without_mixing_original_retrieval_order() -> None:
    chunks = frozen_production_chunks(_dataset())
    reranker = FakeReranker([0.1, 0.9])
    assert rerank_candidates("query", [0, 1], chunks=chunks, reranker=reranker) == [
        1,
        0,
    ]
    assert reranker.calls == [("query", [chunks[0].text, chunks[1].text])]


def test_reranker_ties_keep_candidate_order_deterministically() -> None:
    chunks = frozen_production_chunks(_dataset())
    assert rerank_candidates(
        "query", [1, 0], chunks=chunks, reranker=FakeReranker([0.5, 0.5])
    ) == [1, 0]


def test_reranker_benchmark_uses_separate_dense_and_hybrid_candidate_pools() -> None:
    assert CANDIDATE_DEPTH == 20
    dataset = _dataset()
    chunks = frozen_production_chunks(dataset)
    reranker = FakeReranker()
    evaluation = run_reranker_benchmark(
        dataset,
        chunks=chunks,
        adapter=FakeDenseAdapter(),
        reranker=reranker,
        candidate_depth=2,
    )

    assert len(reranker.calls) == len(dataset.queries) * 2
    assert all(len(passages) == 2 for _, passages in reranker.calls)
    assert [result.retriever_key for result in evaluation.results] == [
        "dense_e5",
        "hybrid_rrf",
        "dense_reranker",
        "hybrid_reranker",
    ]
    assert set(evaluation.results[-1].by_language) == {"en", "tr"}
    assert set(evaluation.results[-1].by_category) == {"factual", "morphology_heavy"}
    assert evaluation.results[-1].parameters["candidate_depth"] == 2


def test_reranker_result_serialization_is_machine_readable(tmp_path) -> None:
    evaluation = RerankerEvaluation(
        results=(
            RetrievalBenchmarkResult("dense_e5", "Dense", {"mrr": 1.0}, {}, {}, {}, {}),
            RetrievalBenchmarkResult(
                "hybrid_rrf", "Hybrid", {"mrr": 0.5}, {}, {}, {}, {}
            ),
            RetrievalBenchmarkResult(
                "dense_reranker",
                "Dense + Reranker",
                {"mrr": 1.0},
                {},
                {},
                {"pairs_scored": 40},
                {
                    "candidate_depth": CANDIDATE_DEPTH,
                    "reranker_model_id": RERANKER_MODEL_ID,
                },
            ),
            RetrievalBenchmarkResult(
                "hybrid_reranker",
                "Hybrid + Reranker",
                {"mrr": 0.75},
                {},
                {},
                {},
                {
                    "candidate_depth": CANDIDATE_DEPTH,
                    "reranker_model_id": RERANKER_MODEL_ID,
                },
            ),
        ),
        diagnostics={"dense_reranker_improves": ["q-en"]},
    )
    save_reranker_results(
        evaluation, dataset_version="v1", output_dir=tmp_path, runtime_metadata={}
    )

    payload = json.loads((tmp_path / "reranker_results_v1.json").read_text())
    with (tmp_path / "reranker_results_v1.csv").open(newline="") as file:
        rows = list(csv.DictReader(file))

    assert len(rows) == 4
    assert payload["diagnostics"]["dense_reranker_improves"] == ["q-en"]
    assert rows[2]["reranker_model_id"] == RERANKER_MODEL_ID
