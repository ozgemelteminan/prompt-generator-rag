import ast
import inspect
import json
import sys
import types
from pathlib import Path

import pytest
from app.document_processing.chunking import StructureAwareChunker
from app.document_processing.models import ChunkingConfig

from evals.src.chunking_eval import (
    DebugHashEmbedder,
    SentenceTransformerEmbedder,
    fixed_size_chunks,
    production_structure_aware_chunks,
    recursive_chunks,
    run_comparison,
    save_results,
)
from evals.src.dataset import (
    EvaluationBlock,
    EvaluationDataset,
    EvaluationDocument,
    EvaluationQuery,
    load_dataset,
    validate_dataset,
)

ROOT = Path(__file__).resolve().parents[2]


def _document() -> EvaluationDocument:
    return EvaluationDocument(
        id="document",
        language="en",
        blocks=(
            EvaluationBlock("b0", "First section", "heading", 0),
            EvaluationBlock(
                "b1", "alpha beta gamma delta", "paragraph", 1, section="First section"
            ),
            EvaluationBlock(
                "b2", "epsilon zeta eta theta", "paragraph", 2, section="First section"
            ),
        ),
    )


def test_dataset_is_valid_and_balanced() -> None:
    dataset = load_dataset(ROOT / "evals/datasets/chunking_eval_v1.json")
    assert len(dataset.documents) == 6
    assert len(dataset.queries) == 42
    assert {document.language for document in dataset.documents} == {"tr", "en"}
    assert {query.category for query in dataset.queries} == {
        "factual",
        "paraphrase",
        "heading_dependent",
        "cross_paragraph",
        "terminology_mismatch",
        "morphology_heavy",
    }


def test_dataset_rejects_unknown_ground_truth_block() -> None:
    document = _document()
    invalid = EvaluationDataset(
        "v1",
        (document,),
        (
            EvaluationQuery(
                "q", "document", "en", "question", frozenset({"missing"}), "factual"
            ),
        ),
    )
    with pytest.raises(ValueError, match="invalid relevant"):
        validate_dataset(invalid)


def test_baselines_and_production_adapter_preserve_source_attribution() -> None:
    document = _document()
    fixed = fixed_size_chunks(document, max_tokens=4, overlap_tokens=1)
    recursive = recursive_chunks(document, target_tokens=5, max_tokens=8)
    production = production_structure_aware_chunks(
        document, config=ChunkingConfig(target_tokens=5, max_tokens=8, overlap_tokens=0)
    )

    assert fixed[0].source_block_ids == frozenset({"b0", "b1"})
    assert all(chunk.source_block_ids <= {"b0", "b1", "b2"} for chunk in recursive)
    assert production[0].source_block_ids == frozenset({"b0"})
    assert production[1].source_block_ids == frozenset({"b1"})
    assert [chunk.chunk_index for chunk in production] == list(range(len(production)))


def test_debug_experiment_is_deterministic_and_reports_groups() -> None:
    document = _document()
    dataset = EvaluationDataset(
        "v1",
        (document,),
        (
            EvaluationQuery(
                "q1", "document", "en", "alpha", frozenset({"b1"}), "factual"
            ),
            EvaluationQuery(
                "q2", "document", "en", "epsilon", frozenset({"b2"}), "paraphrase"
            ),
        ),
    )
    strategies = {"fixed": fixed_size_chunks(document, max_tokens=4, overlap_tokens=0)}

    first = run_comparison(dataset, embedder=DebugHashEmbedder(), strategies=strategies)
    second = run_comparison(
        dataset, embedder=DebugHashEmbedder(), strategies=strategies
    )

    assert first == second
    assert set(first[0].by_category) == {"factual", "paraphrase"}
    assert set(first[0].by_language) == {"en"}


def test_debug_embedder_cannot_write_official_results(tmp_path) -> None:
    with pytest.raises(ValueError, match="Debug hash"):
        save_results(
            [],
            dataset_version="v1",
            embedder=DebugHashEmbedder(),
            output_dir=tmp_path,
            chunker_configurations={},
        )


def test_debug_hash_embedder_remains_non_official_and_deterministic() -> None:
    embedder = DebugHashEmbedder()

    assert embedder.is_official is False
    assert embedder.truncation_rate(["text"]) == 0.0
    assert embedder.encode(["same text"]) == embedder.encode(["same text"])


def test_official_result_metadata_records_runtime_versions(tmp_path) -> None:
    class OfficialEmbedder:
        model_name = "Alibaba-NLP/gte-multilingual-base"
        is_official = True

        def encode(self, texts: list[str]) -> list[list[float]]:
            return [[] for _ in texts]

        def truncation_rate(self, texts: list[str]) -> float:
            return 0.0

    save_results(
        [],
        dataset_version="v1",
        embedder=OfficialEmbedder(),
        output_dir=tmp_path,
        chunker_configurations={"fixed": {"max_tokens": 500}},
        runtime_metadata={
            "torchVersion": "2.11.0",
            "transformersVersion": "4.57.6",
            "sentenceTransformersVersion": "5.6.0",
            "cudaDevice": "A100",
        },
    )

    payload = json.loads((tmp_path / "chunking_results_v1.json").read_text())
    assert payload["runtime"]["transformersVersion"] == "4.57.6"
    assert payload["chunkerConfigurations"]["fixed"]["max_tokens"] == 500


def test_sentence_transformer_remote_code_defaults_to_false(monkeypatch) -> None:
    calls: list[tuple[str, bool]] = []

    class FakeSentenceTransformer:
        def __init__(self, model_name: str, *, trust_remote_code: bool) -> None:
            calls.append((model_name, trust_remote_code))

    monkeypatch.setitem(
        sys.modules,
        "sentence_transformers",
        types.SimpleNamespace(SentenceTransformer=FakeSentenceTransformer),
    )

    embedder = SentenceTransformerEmbedder("example/model")

    assert embedder.trust_remote_code is False
    assert calls == [("example/model", False)]
    assert (
        inspect.signature(SentenceTransformerEmbedder.__init__)
        .parameters["trust_remote_code"]
        .default
        is False
    )


def test_sentence_transformer_forwards_explicit_remote_code_opt_in(monkeypatch) -> None:
    calls: list[tuple[str, bool]] = []

    class FakeSentenceTransformer:
        def __init__(self, model_name: str, *, trust_remote_code: bool) -> None:
            calls.append((model_name, trust_remote_code))

    monkeypatch.setitem(
        sys.modules,
        "sentence_transformers",
        types.SimpleNamespace(SentenceTransformer=FakeSentenceTransformer),
    )

    embedder = SentenceTransformerEmbedder(
        "Alibaba-NLP/gte-multilingual-base", trust_remote_code=True
    )

    assert embedder.trust_remote_code is True
    assert calls == [("Alibaba-NLP/gte-multilingual-base", True)]


def test_sentence_transformer_forwards_explicit_false(monkeypatch) -> None:
    calls: list[tuple[str, bool]] = []

    class FakeSentenceTransformer:
        def __init__(self, model_name: str, *, trust_remote_code: bool) -> None:
            calls.append((model_name, trust_remote_code))

    monkeypatch.setitem(
        sys.modules,
        "sentence_transformers",
        types.SimpleNamespace(SentenceTransformer=FakeSentenceTransformer),
    )

    SentenceTransformerEmbedder("example/model", trust_remote_code=False)

    assert calls == [("example/model", False)]


def test_notebook_cells_are_valid_python_and_configure_production_import_path() -> None:
    notebook = json.loads(
        (ROOT / "notebooks/01_chunking_experiments.ipynb").read_text()
    )
    code = [
        "".join(cell["source"])
        for cell in notebook["cells"]
        if cell["cell_type"] == "code"
    ]

    for cell in code:
        ast.parse(cell)
    setup = code[0]
    initialization = code[1]
    assert "api_root = repository_root / 'apps' / 'api'" in setup
    assert "sys.path.insert(0, str(import_root))" in setup
    assert "fetch', '--all', '--tags', '--prune" in setup
    assert "Stale evaluation modules are already loaded" in setup
    assert "'transformers==4.57.6'" in setup
    assert "'sentence-transformers==5.6.0'" in setup
    assert setup.index("transformers==4.57.6") < setup.index("import transformers")
    assert setup.index("import sentence_transformers") < setup.index("api_root =")
    assert "assert transformers.__version__ == '4.57.6'" in setup
    assert "GPU_NAME = torch.cuda.get_device_name(0)" in setup
    markdown = "".join(
        "".join(cell["source"])
        for cell in notebook["cells"]
        if cell["cell_type"] == "markdown"
    )
    assert "Runtime → Disconnect and delete runtime" in markdown
    assert "inspect.signature(SentenceTransformerEmbedder.__init__)" in initialization
    assert "trust_remote_code=True" in initialization


def test_production_chunker_is_imported_from_the_api_source_of_truth() -> None:
    assert StructureAwareChunker.__module__ == "app.document_processing.chunking"
