from pathlib import Path

import pytest
from app.document_processing.models import ChunkingConfig

from evals.src.chunking_eval import (
    DebugHashEmbedder,
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
