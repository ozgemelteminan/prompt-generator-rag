import csv
import json

from evals.src.dataset import (
    EvaluationBlock,
    EvaluationDataset,
    EvaluationDocument,
    EvaluationQuery,
)
from evals.src.embedding_eval import (
    EmbeddingModelSpec,
    embedding_model_registry,
    frozen_production_chunks,
)
from evals.src.retrieval_eval import (
    BM25_B,
    BM25_K1,
    CSV_FIELDNAMES,
    Bm25Retriever,
    RetrievalBenchmarkResult,
    run_bm25_baseline,
    run_dense_baseline,
    save_retrieval_results,
    tokenize_lexical,
)


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
    english_document = EvaluationDocument(
        id="doc",
        language="en",
        blocks=(
            EvaluationBlock("b0", "Alpha evidence", "paragraph", 0),
            EvaluationBlock("b1", "Beta evidence", "paragraph", 1),
        ),
    )
    turkish_document = EvaluationDocument(
        id="tr-doc",
        language="tr",
        blocks=(EvaluationBlock("tr-b0", "Beta kanıt", "paragraph", 0),),
    )
    return EvaluationDataset(
        "v1",
        (english_document, turkish_document),
        (
            EvaluationQuery("q0", "doc", "en", "alpha", frozenset({"b0"}), "factual"),
            EvaluationQuery(
                "q1", "doc", "en", "beta", frozenset({"b1"}), "hard_paraphrase"
            ),
            EvaluationQuery(
                "q2",
                "tr-doc",
                "tr",
                "beta",
                frozenset({"tr-b0"}),
                "morphology_heavy",
            ),
        ),
    )


def test_bm25_ranking_is_deterministic() -> None:
    retriever = Bm25Retriever(["alpha alpha", "alpha beta", "beta"])
    assert retriever.rank("alpha") == [0, 1, 2]
    assert retriever.rank("alpha") == [0, 1, 2]
    assert retriever.k1 == BM25_K1
    assert retriever.b == BM25_B


def test_bm25_tokenization_preserves_turkish_unicode_words() -> None:
    assert tokenize_lexical("İstanbul'da Çalışma: güvenlik_önlemi") == [
        "istanbul",
        "da",
        "çalışma",
        "güvenlik",
        "önlemi",
    ]


def test_dense_and_sparse_use_the_same_frozen_chunks_and_central_metrics() -> None:
    dataset = _dataset()
    chunks = frozen_production_chunks(dataset)
    adapter = FakeDenseAdapter()
    dense = run_dense_baseline(dataset, chunks=chunks, adapter=adapter)
    sparse = run_bm25_baseline(dataset, chunks=chunks)

    assert adapter.passage_texts == [chunk.text for chunk in chunks]
    assert (
        dense.efficiency["chunk_count"]
        == sparse.efficiency["chunk_count"]
        == len(chunks)
    )
    assert set(dense.metrics) == {
        "recall_at_5",
        "recall_at_10",
        "hit_rate_at_5",
        "mrr",
        "ndcg_at_10",
        "required_block_coverage_at_5",
        "required_block_coverage_at_10",
    }
    assert set(dense.by_language) == {"en", "tr"}
    assert set(sparse.by_category) == {
        "factual",
        "hard_paraphrase",
        "morphology_heavy",
    }


def test_dense_baseline_uses_the_frozen_e5_winner_specification() -> None:
    spec = embedding_model_registry()["multilingual_e5_large_instruct"]
    assert spec.model_id == "intfloat/multilingual-e5-large-instruct"


def test_retrieval_result_serialization_is_machine_readable(tmp_path) -> None:
    results = [
        RetrievalBenchmarkResult(
            "dense_e5",
            "Dense — intfloat/multilingual-e5-large-instruct",
            {"mrr": 1.0},
            {"en": {"mrr": 1.0}},
            {"factual": {"mrr": 1.0}},
            {
                "query_embedding_seconds": 1.0,
                "query_retrieval_seconds": 2.0,
                "chunk_count": 3,
            },
            {"model_id": "intfloat/multilingual-e5-large-instruct"},
        ),
        RetrievalBenchmarkResult(
            "sparse_bm25",
            "Sparse — BM25",
            {"mrr": 0.5},
            {"tr": {"mrr": 0.5}},
            {"morphology_heavy": {"mrr": 0.5}},
            {
                "index_build_seconds": 0.1,
                "query_retrieval_seconds": 0.2,
                "chunk_count": 3,
            },
            {"bm25_k1": BM25_K1, "bm25_b": BM25_B, "tokenizer": "unicode_casefold"},
        ),
    ]
    save_retrieval_results(
        results, dataset_version="v1", output_dir=tmp_path, runtime_metadata={}
    )

    payload = json.loads((tmp_path / "sparse_dense_results_v1.json").read_text())
    with (tmp_path / "sparse_dense_results_v1.csv").open(newline="") as file:
        rows = list(csv.DictReader(file))

    assert [result["retriever_key"] for result in payload["results"]] == [
        "dense_e5",
        "sparse_bm25",
    ]
    assert tuple(rows[0]) == CSV_FIELDNAMES
    assert rows[0]["index_build_seconds"] == ""
    assert rows[1]["query_embedding_seconds"] == ""
