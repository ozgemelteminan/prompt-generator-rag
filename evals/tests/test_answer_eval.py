import json
import sys
from pathlib import Path

from evals.src.answer_eval import (
    AnswerEvalCase,
    ExpectedFact,
    _retrieved_chunk,
    aggregate_outcomes,
    evaluate_answer,
    load_answer_eval_dataset,
    run_fixture_evaluation,
    write_answer_eval_artifacts,
)

ROOT = Path(__file__).resolve().parents[2]
DATASET_PATH = ROOT / "evals/datasets/answer_eval_v1.json"


def _configure_production_imports() -> None:
    sys.path.insert(0, str(ROOT / "apps/api"))
    sys.path.insert(0, str(ROOT / "packages/prompt-engine"))


def _case() -> AnswerEvalCase:
    return AnswerEvalCase(
        id="case",
        document_id="doc",
        language="en",
        category="factual",
        query="Question?",
        answerable=True,
        fixture_retrieved_block_ids=("block-1",),
        expected_facts=(
            ExpectedFact(
                id="fact",
                accepted_answers=("The launch is Monday",),
                source_block_ids=frozenset({"block-1"}),
            ),
        ),
        fixture_answer="The launch is Monday. [1]",
    )


def test_answer_dataset_is_small_bilingual_and_reviewable() -> None:
    dataset = load_answer_eval_dataset(DATASET_PATH)

    assert dataset.version == "answer-eval-v1"
    assert len(dataset.cases) == 12
    assert sum(case.language == "tr" for case in dataset.cases) == 6
    assert sum(case.language == "en" for case in dataset.cases) == 6
    assert sum(case.answerable for case in dataset.cases) == 8
    assert sum(not case.answerable for case in dataset.cases) == 4
    assert {case.category for case in dataset.cases} >= {
        "factual",
        "safety",
        "cross_paragraph",
        "insufficient_evidence",
    }


def test_fact_coverage_citations_and_groundedness_are_deterministic() -> None:
    outcome = evaluate_answer(
        _case(),
        state="answer",
        answer="The launch is Monday. [1]",
        citation_source_blocks={1: frozenset({"block-1"})},
        source_public_fields=(frozenset({"citation_id", "chunk_id"}),),
    )

    assert outcome.answer_correctness == 1.0
    assert outcome.citation_validity == 1.0
    assert outcome.citation_correctness == 1.0
    assert outcome.citation_completeness == 1.0
    assert outcome.faithfulness == 1.0
    assert outcome.failures == ()


def test_uncited_and_wrong_source_claims_are_detected() -> None:
    uncited = evaluate_answer(
        _case(),
        state="answer",
        answer="The launch is Monday.",
        citation_source_blocks={1: frozenset({"block-1"})},
    )
    wrong_source = evaluate_answer(
        _case(),
        state="answer",
        answer="The launch is Monday. [1]",
        citation_source_blocks={1: frozenset({"other-block"})},
    )

    assert uncited.citation_completeness == uncited.faithfulness == 0.0
    assert "expected claim is uncited or unsupported" in uncited.failures
    assert wrong_source.citation_correctness == wrong_source.faithfulness == 0.0


def test_adjacent_sentence_citations_are_associated_with_their_own_claims() -> None:
    case = AnswerEvalCase(
        id="two-facts",
        document_id="doc",
        language="en",
        category="factual",
        query="Question?",
        answerable=True,
        fixture_retrieved_block_ids=("block-1", "block-2"),
        expected_facts=(
            ExpectedFact("first", ("The launch is Monday",), frozenset({"block-1"})),
            ExpectedFact("second", ("The review is Tuesday",), frozenset({"block-2"})),
        ),
        fixture_answer="The launch is Monday. [1] The review is Tuesday. [2]",
    )
    outcome = evaluate_answer(
        case,
        state="answer",
        answer=case.fixture_answer,
        citation_source_blocks={1: frozenset({"block-1"}), 2: frozenset({"block-2"})},
    )

    assert outcome.citation_correctness == outcome.citation_completeness == 1.0


def test_invalid_citations_and_nonpublic_provenance_are_detected() -> None:
    outcome = evaluate_answer(
        _case(),
        state="answer",
        answer="The launch is Monday. [2]",
        citation_source_blocks={1: frozenset({"block-1"})},
        source_public_fields=(frozenset({"citation_id", "storage_path"}),),
    )

    assert outcome.citation_validity == 0.0
    assert "answer contains an invalid citation" in outcome.failures
    assert "source metadata exposes a non-public field" in outcome.failures


def test_unanswerable_cases_require_clean_insufficient_evidence() -> None:
    case = AnswerEvalCase(
        id="unanswerable",
        document_id="doc",
        language="tr",
        category="insufficient_evidence",
        query="?",
        answerable=False,
        fixture_retrieved_block_ids=(),
        expected_facts=(),
        fixture_answer=None,
    )

    success = evaluate_answer(
        case,
        state="insufficient_evidence",
        answer=None,
        citation_source_blocks={},
    )
    failure = evaluate_answer(
        case,
        state="answer",
        answer="Unsupported answer [1]",
        citation_source_blocks={1: frozenset({"block"})},
    )

    assert success.insufficient_evidence_success == 1.0
    assert failure.insufficient_evidence_success == 0.0
    assert (
        "unanswerable case did not return clean insufficient evidence"
        in failure.failures
    )


def test_context_sources_preserve_fixture_provenance_without_fabricated_metadata() -> (
    None
):
    _configure_production_imports()
    from app.services.context import ContextBuilder

    dataset = load_answer_eval_dataset(DATASET_PATH)
    case = next(
        item for item in dataset.cases if item.id == "m62-en-context-provenance"
    )
    context = ContextBuilder(max_tokens=2_000).build(
        [_retrieved_chunk(dataset, case, "en-ret-4", 0)]
    )

    source = context.sources[0]
    assert source.citation_id == 1
    assert source.chunk_id == "en-ret-4"
    assert source.document_id == case.document_id
    assert source.filename == "doc-en-retrieval.json"
    assert source.page_start is source.page_end is None
    assert "storage" not in source.__dict__ and "embedding" not in source.__dict__


def test_fixture_run_uses_production_orchestration_and_serializes_results(
    tmp_path: Path,
) -> None:
    _configure_production_imports()
    dataset = load_answer_eval_dataset(DATASET_PATH)
    outcomes = run_fixture_evaluation(dataset)
    payload = write_answer_eval_artifacts(outcomes, output_dir=tmp_path, mode="fixture")

    assert len(outcomes) == 12
    assert payload["status"] == "fixture_only"
    assert payload["metrics"]["overall"]["answer_correctness"] == 1.0
    assert payload["metrics"]["byLanguage"]["tr"]["case_count"] == 6
    assert (
        payload["metrics"]["byAnswerability"]["unanswerable"][
            "insufficient_evidence_success"
        ]
        == 1.0
    )
    assert (
        json.loads((tmp_path / "answer_eval_v1.json").read_text())["metrics"]
        == payload["metrics"]
    )
    assert (tmp_path / "answer_eval_v1.csv").read_text().startswith("case_id,")
    assert "fixture_only" in (tmp_path / "answer_eval_v1.md").read_text()
    assert aggregate_outcomes(outcomes) == payload["metrics"]
    assert outcomes == run_fixture_evaluation(dataset)
