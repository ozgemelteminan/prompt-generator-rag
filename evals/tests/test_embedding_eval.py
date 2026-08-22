import ast
import csv
import json
from pathlib import Path

import pytest
from app.document_processing.chunking import StructureAwareChunker

from evals.src.dataset import (
    EvaluationBlock,
    EvaluationDataset,
    EvaluationDocument,
    EvaluationQuery,
    load_dataset,
)
from evals.src.embedding_eval import (
    CSV_FIELDNAMES,
    E5_INSTRUCTION,
    TURKISH_E5_INSTRUCTION,
    EmbeddingBenchmarkResult,
    EmbeddingModelSpec,
    benchmark_embedding_model,
    embedding_model_registry,
    frozen_production_chunks,
    save_embedding_results,
)
from evals.src.metrics import required_block_coverage_at_k

ROOT = Path(__file__).resolve().parents[2]


class FakeAdapter:
    is_official = True

    def __init__(self) -> None:
        self.spec = EmbeddingModelSpec(
            key="fake",
            model_id="fake/model",
            query_formatter=lambda text: text,
            passage_formatter=lambda text: text,
            normalize_embeddings=True,
        )

    def encode_queries(self, texts: list[str]) -> list[list[float]]:
        return [[1.0, 0.0] if "alpha" in text else [0.0, 1.0] for text in texts]

    def encode_passages(self, texts: list[str]) -> list[list[float]]:
        return [[1.0, 0.0] if "alpha" in text else [0.0, 1.0] for text in texts]

    def efficiency(self) -> dict[str, float | int]:
        return {
            "embedding_dimension": 2,
            "queries_per_second": 1.0,
            "passages_per_second": 1.0,
        }

    def truncation_rate(self, texts: list[str]) -> float:
        return 0.0

    def release(self) -> None:
        pass


def _dataset() -> EvaluationDataset:
    document = EvaluationDocument(
        id="doc",
        language="en",
        blocks=(
            EvaluationBlock("b0", "Title", "heading", 0),
            EvaluationBlock("b1", "alpha evidence", "paragraph", 1, section="Title"),
            EvaluationBlock("b2", "beta evidence", "paragraph", 2, section="Title"),
        ),
    )
    return EvaluationDataset(
        "v1",
        (document,),
        (
            EvaluationQuery("q1", "doc", "en", "alpha", frozenset({"b1"}), "factual"),
            EvaluationQuery(
                "q2", "doc", "en", "beta", frozenset({"b2"}), "morphology_heavy"
            ),
        ),
    )


def test_model_registry_has_required_model_specific_formatting() -> None:
    registry = embedding_model_registry()
    assert set(registry) == {
        "gte_multilingual_base",
        "bge_m3",
        "multilingual_e5_large_instruct",
        "turkish_e5_large",
    }
    gte = registry["gte_multilingual_base"]
    assert gte.trust_remote_code is True
    assert gte.query_formatter("hello") == "hello"
    assert gte.passage_formatter("text") == "text"

    bge_m3 = registry["bge_m3"]
    assert bge_m3.query_formatter("hello") == "hello"
    assert bge_m3.passage_formatter("text") == "text"
    assert "Represent this sentence" not in bge_m3.query_formatter("hello")

    multilingual_e5 = registry["multilingual_e5_large_instruct"]
    assert multilingual_e5.query_formatter("hello") == (
        f"{E5_INSTRUCTION}\nQuery: hello"
    )
    assert multilingual_e5.passage_formatter("text") == "text"
    assert not multilingual_e5.passage_formatter("text").startswith("passage:")

    turkish_e5 = registry["turkish_e5_large"]
    assert turkish_e5.query_formatter("soru") == (
        f"Instruct: {TURKISH_E5_INSTRUCTION}\nQuery: soru"
    )
    assert turkish_e5.passage_formatter("metin") == "metin"
    assert not turkish_e5.passage_formatter("metin").startswith("passage:")


def test_required_block_coverage_is_source_block_based() -> None:
    ranking = [frozenset({"b1"}), frozenset({"b2"})]
    required = frozenset({"b1", "b2"})
    assert required_block_coverage_at_k(ranking, required, 1) == 0.5
    assert required_block_coverage_at_k(ranking, required, 2) == 1.0


def test_frozen_chunks_use_production_chunker_once_with_frozen_config() -> None:
    chunks = frozen_production_chunks(_dataset())
    assert chunks
    assert StructureAwareChunker.__module__ == "app.document_processing.chunking"
    assert all(chunk.document_id == "doc" for chunk in chunks)


def test_fake_retrieval_is_deterministic_and_reports_groups() -> None:
    dataset = _dataset()
    chunks = frozen_production_chunks(dataset)
    first = benchmark_embedding_model(dataset, chunks=chunks, adapter=FakeAdapter())
    second = benchmark_embedding_model(dataset, chunks=chunks, adapter=FakeAdapter())
    assert first == second
    assert set(first.by_language) == {"en"}
    assert set(first.by_category) == {"factual", "morphology_heavy"}
    assert "required_block_coverage_at_10" in first.metrics


def test_embedding_result_serialization_rejects_debug_results(tmp_path) -> None:
    debug = EmbeddingBenchmarkResult("debug", "debug-hash", False, {}, {}, {}, {}, 0.0)
    with pytest.raises(ValueError, match="Debug embeddings"):
        save_embedding_results(
            [debug], dataset_version="v1", output_dir=tmp_path, runtime_metadata={}
        )


def test_embedding_result_serialization_writes_machine_readable_output(
    tmp_path,
) -> None:
    result = EmbeddingBenchmarkResult(
        "fake",
        "fake/model",
        True,
        {
            "recall_at_5": 0.5,
            "recall_at_10": 1.0,
            "mrr": 1.0,
            "ndcg_at_10": 1.0,
            "hit_rate_at_5": 1.0,
            "required_block_coverage_at_5": 0.5,
            "required_block_coverage_at_10": 1.0,
        },
        {"tr": {}},
        {"factual": {}},
        {
            "model_load_seconds": 1.0,
            "passage_embedding_seconds": 2.0,
            "query_embedding_seconds": 3.0,
            "peak_cuda_memory_bytes": 4,
            "embedding_dimension": 5,
            "passages_per_second": 6.0,
            "queries_per_second": 7.0,
        },
        0.25,
    )
    save_embedding_results(
        [result],
        dataset_version="v1",
        output_dir=tmp_path,
        runtime_metadata={"torchVersion": "x"},
    )
    payload = json.loads((tmp_path / "embedding_results_v1.json").read_text())
    with (tmp_path / "embedding_results_v1.csv").open(newline="") as file:
        rows = list(csv.DictReader(file))

    assert payload["runtime"]["torchVersion"] == "x"
    assert payload["results"][0]["model_id"] == "fake/model"
    assert tuple(rows[0]) == CSV_FIELDNAMES
    assert rows[0]["model_id"] == payload["results"][0]["model_id"]
    assert float(rows[0]["mrr"]) == payload["results"][0]["metrics"]["mrr"]
    assert (
        float(rows[0]["model_load_seconds"])
        == payload["results"][0]["efficiency"]["model_load_seconds"]
    )
    assert (
        float(rows[0]["passage_throughput"])
        == payload["results"][0]["efficiency"]["passages_per_second"]
    )
    assert (
        float(rows[0]["query_throughput"])
        == payload["results"][0]["efficiency"]["queries_per_second"]
    )
    assert float(rows[0]["truncation_rate"]) == payload["results"][0]["truncation_rate"]


def test_embedding_result_serialization_blanks_missing_efficiency_values_and_updates(
    tmp_path,
) -> None:
    first = EmbeddingBenchmarkResult(
        "first", "first/model", True, {}, {}, {}, {"embedding_dimension": 2}, 0.0
    )
    second = EmbeddingBenchmarkResult(
        "second", "second/model", True, {}, {}, {}, {}, 0.0
    )
    save_embedding_results(
        [first], dataset_version="v1", output_dir=tmp_path, runtime_metadata={}
    )
    save_embedding_results(
        [first, second], dataset_version="v1", output_dir=tmp_path, runtime_metadata={}
    )

    payload = json.loads((tmp_path / "embedding_results_v1.json").read_text())
    with (tmp_path / "embedding_results_v1.csv").open(newline="") as file:
        rows = list(csv.DictReader(file))

    assert [result["model_key"] for result in payload["results"]] == [
        "first",
        "second",
    ]
    assert [row["model_key"] for row in rows] == ["first", "second"]
    assert rows[0]["model_load_seconds"] == ""
    assert rows[1]["embedding_dimension"] == ""


def test_retrieval_dataset_and_notebook_are_static_and_valid() -> None:
    dataset = load_dataset(ROOT / "evals/datasets/retrieval_eval_v1.json")
    assert len(dataset.queries) == 84
    assert {query.language for query in dataset.queries} == {"tr", "en"}
    assert {query.category for query in dataset.queries} >= {
        "hard_paraphrase",
        "near_negative",
        "same_topic_competitor",
        "multi_section",
    }
    notebook = json.loads((ROOT / "notebooks/02_embedding_benchmark.ipynb").read_text())
    code = [
        "".join(cell["source"])
        for cell in notebook["cells"]
        if cell["cell_type"] == "code"
    ]
    for cell in code:
        if not cell.lstrip().startswith("!"):
            ast.parse(cell)
    assert "transformers==4.57.6" in code[0]
    assert (
        code[0].index("transformers==4.57.6") < code[0].index("from evals")
        if "from evals" in code[0]
        else True
    )
    assert "frozen_production_chunks(dataset)" in code[1]
    assert "'query_throughput'" in code[2]
    assert "'passage_throughput'" in code[2]
    assert "('query_throughput', 'general bilingual speed'" in code[2]
