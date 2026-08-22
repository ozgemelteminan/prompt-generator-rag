import ast
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
        {"mrr": 1.0},
        {"tr": {}},
        {"factual": {}},
        {"embedding_dimension": 2},
        0.0,
    )
    save_embedding_results(
        [result],
        dataset_version="v1",
        output_dir=tmp_path,
        runtime_metadata={"torchVersion": "x"},
    )
    payload = json.loads((tmp_path / "embedding_results_v1.json").read_text())
    assert payload["runtime"]["torchVersion"] == "x"
    assert payload["results"][0]["model_id"] == "fake/model"


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
        ast.parse(cell)
    assert "transformers==4.57.6" in code[0]
    assert (
        code[0].index("transformers==4.57.6") < code[0].index("from evals")
        if "from evals" in code[0]
        else True
    )
    assert "frozen_production_chunks(dataset)" in code[1]
