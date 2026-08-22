"""Deterministic M6.2 answer, grounding, and citation evaluation."""

import argparse
import csv
import json
import re
from collections.abc import Callable, Iterable
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Literal

from evals.src.dataset import load_dataset

_CITATION_PATTERN = re.compile(r"\[(\d+)\]")
_SENTENCE_ENDING = re.compile(r"[.!?…]")
_PUBLIC_SOURCE_FIELDS = {
    "citation_id",
    "document_id",
    "chunk_id",
    "filename",
    "page_start",
    "page_end",
    "section",
    "heading",
    "excerpt",
    "similarity",
}


@dataclass(frozen=True)
class ExpectedFact:
    id: str
    accepted_answers: tuple[str, ...]
    source_block_ids: frozenset[str]


@dataclass(frozen=True)
class AnswerEvalCase:
    id: str
    document_id: str
    language: Literal["tr", "en"]
    category: str
    query: str
    answerable: bool
    fixture_retrieved_block_ids: tuple[str, ...]
    expected_facts: tuple[ExpectedFact, ...]
    fixture_answer: str | None


@dataclass(frozen=True)
class AnswerEvalDataset:
    version: str
    source_corpus_version: str
    source_blocks: dict[str, Any]
    cases: tuple[AnswerEvalCase, ...]


@dataclass(frozen=True)
class AnswerEvalOutcome:
    case_id: str
    language: str
    category: str
    answerable: bool
    state: str
    answer: str | None
    source_citation_ids: tuple[int, ...]
    citation_validity: float | None
    answer_correctness: float | None
    citation_correctness: float | None
    citation_completeness: float | None
    faithfulness: float | None
    insufficient_evidence_success: float | None
    failures: tuple[str, ...]


def load_answer_eval_dataset(path: Path) -> AnswerEvalDataset:
    raw = json.loads(path.read_text(encoding="utf-8"))
    source_corpus = load_dataset(path.parent / raw["sourceCorpus"])
    documents = {document.id: document for document in source_corpus.documents}
    source_blocks = {
        block.id: block
        for document in source_corpus.documents
        for block in document.blocks
    }
    cases = tuple(
        AnswerEvalCase(
            id=item["caseId"],
            document_id=item["documentId"],
            language=item["language"],
            category=item["category"],
            query=item["query"],
            answerable=item["answerable"],
            fixture_retrieved_block_ids=tuple(item["fixtureRetrievedBlockIds"]),
            expected_facts=tuple(
                ExpectedFact(
                    id=fact["factId"],
                    accepted_answers=tuple(fact["acceptedAnswers"]),
                    source_block_ids=frozenset(fact["sourceBlockIds"]),
                )
                for fact in item["expectedFacts"]
            ),
            fixture_answer=item["fixtureAnswer"],
        )
        for item in raw["cases"]
    )
    dataset = AnswerEvalDataset(
        version=raw["version"],
        source_corpus_version=source_corpus.version,
        source_blocks=source_blocks,
        cases=cases,
    )
    _validate_answer_eval_dataset(dataset, documents)
    return dataset


def _validate_answer_eval_dataset(
    dataset: AnswerEvalDataset, documents: dict[str, Any]
) -> None:
    case_ids = [case.id for case in dataset.cases]
    if not dataset.cases or len(case_ids) != len(set(case_ids)):
        raise ValueError("Answer evaluation cases must have unique IDs.")
    for case in dataset.cases:
        document = documents.get(case.document_id)
        if document is None or document.language != case.language:
            raise ValueError(f"Case {case.id} has an invalid document or language.")
        retrieved = set(case.fixture_retrieved_block_ids)
        if not retrieved <= set(dataset.source_blocks):
            raise ValueError(
                f"Case {case.id} references an unknown retrieved source block."
            )
        if any(
            dataset.source_blocks[block_id] not in document.blocks
            for block_id in retrieved
        ):
            raise ValueError(f"Case {case.id} retrieves a block from another document.")
        fact_ids = [fact.id for fact in case.expected_facts]
        if len(fact_ids) != len(set(fact_ids)):
            raise ValueError(f"Case {case.id} has duplicate fact IDs.")
        for fact in case.expected_facts:
            if not fact.accepted_answers or not fact.source_block_ids <= retrieved:
                raise ValueError(
                    f"Case {case.id} has unsupported expected-fact labels."
                )
        if case.answerable != bool(case.expected_facts):
            raise ValueError(f"Case {case.id} answerability and facts disagree.")
        if case.answerable != bool(case.fixture_retrieved_block_ids):
            raise ValueError(
                f"Case {case.id} answerability and fixture retrieval disagree."
            )
        if case.answerable != bool(case.fixture_answer):
            raise ValueError(
                f"Case {case.id} answerability and fixture answer disagree."
            )


def evaluate_answer(
    case: AnswerEvalCase,
    *,
    state: str,
    answer: str | None,
    citation_source_blocks: dict[int, frozenset[str]],
    source_public_fields: Iterable[frozenset[str]] = (),
) -> AnswerEvalOutcome:
    """Score only labeled facts; unsupported free-form claims remain a stated limitation."""
    citations = tuple(
        int(match.group(1)) for match in _CITATION_PATTERN.finditer(answer or "")
    )
    valid_ids = set(citation_source_blocks)
    validity = (
        (sum(citation in valid_ids for citation in citations) / len(citations))
        if citations
        else 1.0
    )
    provenance_is_safe = all(
        fields <= _PUBLIC_SOURCE_FIELDS for fields in source_public_fields
    )
    failures: list[str] = []
    if not provenance_is_safe:
        failures.append("source metadata exposes a non-public field")
    if not case.answerable:
        success = float(
            state == "insufficient_evidence"
            and answer is None
            and not citations
            and not citation_source_blocks
        )
        if not success:
            failures.append(
                "unanswerable case did not return clean insufficient evidence"
            )
        return AnswerEvalOutcome(
            case_id=case.id,
            language=case.language,
            category=case.category,
            answerable=False,
            state=state,
            answer=answer,
            source_citation_ids=tuple(sorted(valid_ids)),
            citation_validity=validity,
            answer_correctness=None,
            citation_correctness=None,
            citation_completeness=None,
            faithfulness=None,
            insufficient_evidence_success=success,
            failures=tuple(failures),
        )
    if state != "answer" or not answer:
        failures.append("answerable case did not produce an answer")
        return AnswerEvalOutcome(
            case_id=case.id,
            language=case.language,
            category=case.category,
            answerable=True,
            state=state,
            answer=answer,
            source_citation_ids=tuple(sorted(valid_ids)),
            citation_validity=validity,
            answer_correctness=0.0,
            citation_correctness=0.0,
            citation_completeness=0.0,
            faithfulness=0.0,
            insufficient_evidence_success=None,
            failures=tuple(failures),
        )

    present_facts = [
        fact for fact in case.expected_facts if _fact_citations(answer, fact)
    ]
    supported_facts = [
        fact
        for fact in present_facts
        if any(
            citation_source_blocks.get(citation_id, frozenset()) & fact.source_block_ids
            for citation_id in _fact_citations(answer, fact)
        )
    ]
    cited_fact_associations = [
        (fact, citation_id)
        for fact in present_facts
        for citation_id in _fact_citations(answer, fact)
    ]
    supported_associations = [
        (fact, citation_id)
        for fact, citation_id in cited_fact_associations
        if citation_source_blocks.get(citation_id, frozenset()) & fact.source_block_ids
    ]
    if validity < 1.0:
        failures.append("answer contains an invalid citation")
    if len(present_facts) != len(case.expected_facts):
        failures.append("expected fact is missing")
    if len(supported_facts) != len(case.expected_facts):
        failures.append("expected claim is uncited or unsupported")
    return AnswerEvalOutcome(
        case_id=case.id,
        language=case.language,
        category=case.category,
        answerable=True,
        state=state,
        answer=answer,
        source_citation_ids=tuple(sorted(valid_ids)),
        citation_validity=validity,
        answer_correctness=len(present_facts) / len(case.expected_facts),
        citation_correctness=(
            len(supported_associations) / len(cited_fact_associations)
            if cited_fact_associations
            else 0.0
        ),
        citation_completeness=len(supported_facts) / len(case.expected_facts),
        faithfulness=len(supported_facts) / len(present_facts)
        if present_facts
        else 0.0,
        insufficient_evidence_success=None,
        failures=tuple(failures),
    )


def _fact_citations(answer: str, fact: ExpectedFact) -> tuple[int, ...]:
    answer_folded = answer.casefold()
    for accepted_answer in fact.accepted_answers:
        start = answer_folded.find(accepted_answer.casefold())
        if start < 0:
            continue
        sentence_start = max(
            (match.end() for match in _SENTENCE_ENDING.finditer(answer[:start])),
            default=0,
        )
        while sentence_start < len(answer) and answer[sentence_start].isspace():
            sentence_start += 1
        while answer[sentence_start : sentence_start + 1] == "[":
            citation_match = _CITATION_PATTERN.match(answer, sentence_start)
            if citation_match is None:
                break
            sentence_start = citation_match.end()
            while sentence_start < len(answer) and answer[sentence_start].isspace():
                sentence_start += 1
        sentence_end_match = _SENTENCE_ENDING.search(answer, start)
        sentence_end = sentence_end_match.end() if sentence_end_match else len(answer)
        while sentence_end < len(answer) and answer[sentence_end].isspace():
            sentence_end += 1
        while answer[sentence_end : sentence_end + 1] == "[":
            citation_match = _CITATION_PATTERN.match(answer, sentence_end)
            if citation_match is None:
                break
            sentence_end = citation_match.end()
            while sentence_end < len(answer) and answer[sentence_end].isspace():
                sentence_end += 1
        return tuple(
            int(match.group(1))
            for match in _CITATION_PATTERN.finditer(answer[sentence_start:sentence_end])
        )
    return ()


def run_fixture_evaluation(
    dataset: AnswerEvalDataset,
    *,
    generation_backend_factory: Callable[[AnswerEvalCase], Any] | None = None,
) -> tuple[AnswerEvalOutcome, ...]:
    """Run production grounded orchestration with reviewed retrieval/generation fixtures."""
    from app.services.context import ContextBuilder
    from app.services.rag import GroundedRagService
    from app.services.retrieval import RetrievedChunk
    from prompt_engine.execution import ExecutionResult

    outcomes: list[AnswerEvalOutcome] = []
    for case in dataset.cases:
        retrieved = [
            _retrieved_chunk(dataset, case, block_id, index)
            for index, block_id in enumerate(case.fixture_retrieved_block_ids)
        ]

        class _FixtureRetrieval:
            def search(
                self, *, _results: list[RetrievedChunk] = retrieved, **_: object
            ) -> list[RetrievedChunk]:
                return _results

        fixture_answer = case.fixture_answer

        class _FixtureGeneration:
            def execute(
                self, _: str, *, _answer: str | None = fixture_answer
            ) -> ExecutionResult:
                if _answer is None:
                    raise AssertionError(
                        "Generation must not run for an unanswerable fixture."
                    )
                return ExecutionResult(output=_answer)

        backend = (
            generation_backend_factory(case)
            if generation_backend_factory is not None
            else _FixtureGeneration()
        )
        result = GroundedRagService(
            retrieval_service=_FixtureRetrieval(),  # type: ignore[arg-type]
            context_builder=ContextBuilder(max_tokens=2_000),
            generation_backend=backend,
        ).ask(query=case.query)
        source_blocks = {
            source.citation_id: frozenset({source.chunk_id})
            for source in result.sources
        }
        outcomes.append(
            evaluate_answer(
                case,
                state=result.state,
                answer=result.answer,
                citation_source_blocks=source_blocks,
                source_public_fields=(
                    frozenset(source.__dict__) for source in result.sources
                ),
            )
        )
    return tuple(outcomes)


def run_provider_fixture_evaluation(
    dataset: AnswerEvalDataset,
) -> tuple[AnswerEvalOutcome, ...]:
    """Opt-in answer-generation run over the same reviewed fixture contexts."""
    from app.core.config import Settings
    from app.infrastructure.llm import ProviderConfigurationError, create_llm_provider

    try:
        backend = create_llm_provider(Settings())
    except ProviderConfigurationError as error:
        raise ValueError(str(error)) from error
    return run_fixture_evaluation(dataset, generation_backend_factory=lambda _: backend)


def _retrieved_chunk(
    dataset: AnswerEvalDataset, case: AnswerEvalCase, block_id: str, index: int
) -> Any:
    from app.services.retrieval import RetrievedChunk

    block = dataset.source_blocks[block_id]
    return RetrievedChunk(
        chunk_id=block.id,
        document_id=case.document_id,
        filename=f"{case.document_id}.json",
        chunk_index=index,
        text=block.text,
        distance=0.01 + index / 100,
        similarity=0.99 - index / 100,
        page_start=block.page_number,
        page_end=block.page_number,
        section=block.section,
        heading=block.section,
        source_block_start=block.order_index,
        source_block_end=block.order_index,
    )


def aggregate_outcomes(
    outcomes: Iterable[AnswerEvalOutcome],
) -> dict[str, dict[str, float | int]]:
    values = tuple(outcomes)
    return {
        "overall": _aggregate(values),
        "byLanguage": {
            language: _aggregate(item for item in values if item.language == language)
            for language in ("tr", "en")
        },
        "byCategory": {
            category: _aggregate(item for item in values if item.category == category)
            for category in sorted({item.category for item in values})
        },
        "byAnswerability": {
            "answerable": _aggregate(item for item in values if item.answerable),
            "unanswerable": _aggregate(item for item in values if not item.answerable),
        },
    }


def _aggregate(outcomes: Iterable[AnswerEvalOutcome]) -> dict[str, float | int]:
    items = tuple(outcomes)
    result: dict[str, float | int] = {"case_count": len(items)}
    for field in (
        "answer_correctness",
        "citation_validity",
        "citation_correctness",
        "citation_completeness",
        "faithfulness",
        "insufficient_evidence_success",
    ):
        values = [
            getattr(item, field) for item in items if getattr(item, field) is not None
        ]
        result[field] = sum(values) / len(values) if values else 0.0
    return result


CSV_FIELDNAMES = (
    "case_id",
    "language",
    "category",
    "answerable",
    "state",
    "answer_correctness",
    "citation_validity",
    "citation_correctness",
    "citation_completeness",
    "faithfulness",
    "insufficient_evidence_success",
    "failures",
)


def write_answer_eval_artifacts(
    outcomes: tuple[AnswerEvalOutcome, ...], *, output_dir: Path, mode: str
) -> dict[str, Any]:
    """Serialize M6.2 outputs without claiming fixture metrics are live-model quality."""
    output_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "experimentVersion": "m6.2",
        "datasetVersion": "answer-eval-v1",
        "status": "fixture_only" if mode == "fixture" else "provider_run",
        "execution": {
            "mode": mode,
            "orchestration": "production GroundedRagService + ContextBuilder",
            "retrieval": "reviewed deterministic fixture",
            "generation": "reviewed deterministic fixture"
            if mode == "fixture"
            else "configured provider",
        },
        "metrics": aggregate_outcomes(outcomes),
        "outcomes": [asdict(outcome) for outcome in outcomes],
        "failureExamples": [
            asdict(outcome) for outcome in outcomes if outcome.failures
        ][:5],
        "limitations": [
            "Fixture results validate the answer evaluation harness; they are not a real-provider answer-quality claim.",
            "Deterministic scoring covers only explicitly labeled facts and source blocks; it cannot detect every unsupported free-form claim.",
            "The fixture path uses reviewed source blocks, not a live PostgreSQL retrieval index. M6.1 separately covers production retrieval parity.",
        ],
    }
    (output_dir / "answer_eval_v1.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    with (output_dir / "answer_eval_v1.csv").open(
        "w", encoding="utf-8", newline=""
    ) as file:
        writer = csv.DictWriter(file, fieldnames=CSV_FIELDNAMES)
        writer.writeheader()
        writer.writerows(
            {
                **{
                    field: getattr(outcome, field)
                    for field in CSV_FIELDNAMES
                    if field not in {"failures"}
                },
                "failures": " | ".join(outcome.failures),
            }
            for outcome in outcomes
        )
    overall = payload["metrics"]["overall"]
    score_fields = (
        "answer_correctness",
        "citation_validity",
        "citation_correctness",
        "citation_completeness",
        "faithfulness",
        "insufficient_evidence_success",
    )
    breakdown_rows = "\n".join(
        f"| {name} | {metrics['case_count']} | "
        + " | ".join(f"{metrics[field]:.3f}" for field in score_fields)
        + " |"
        for name, metrics in (
            *payload["metrics"]["byLanguage"].items(),
            *payload["metrics"]["byAnswerability"].items(),
            *payload["metrics"]["byCategory"].items(),
        )
    )
    (output_dir / "answer_eval_v1.md").write_text(
        "# M6.2 answer, faithfulness, and citation evaluation\n\n"
        f"Execution status: **{payload['status']}** ({mode}).\n\n"
        "## Overall\n\n"
        "| Metric | Score |\n| --- | ---: |\n"
        + "\n".join(
            f"| {field} | {overall[field]:.3f} |"
            for field in (
                "answer_correctness",
                "citation_validity",
                "citation_correctness",
                "citation_completeness",
                "faithfulness",
                "insufficient_evidence_success",
            )
        )
        + "\n\n## Failure examples\n\n"
        + (
            "None in this run.\n"
            if not payload["failureExamples"]
            else "\n".join(
                f"- `{item['case_id']}`: {', '.join(item['failures'])}"
                for item in payload["failureExamples"]
            )
            + "\n"
        )
        + "\n## Language, answerability, and category breakdown\n\n"
        + "| Group | Cases | Answer correctness | Citation validity | Citation correctness | Citation completeness | Faithfulness | Insufficient evidence |\n"
        + "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |\n"
        + breakdown_rows
        + "\n"
        + "\n## Limitations\n\n"
        + "\n".join(f"- {item}" for item in payload["limitations"])
        + "\n\n## Optional provider run\n\n"
        + "This uses the same reviewed fixture contexts and makes one configured-provider call for each answerable case; it does not replace the M6.1 PostgreSQL smoke test.\n\n"
        + "```bash\nLLM_PROVIDER=groq GROQ_API_KEY=<key> PYTHONPATH=apps/api:packages/prompt-engine python -m evals.src.answer_eval --mode provider\n```\n"
        + "\n",
        encoding="utf-8",
    )
    return payload


def _main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--dataset", type=Path, default=Path("evals/datasets/answer_eval_v1.json")
    )
    parser.add_argument("--output-dir", type=Path, default=Path("evals/results/final"))
    parser.add_argument("--mode", choices=("fixture", "provider"), default="fixture")
    arguments = parser.parse_args()
    dataset = load_answer_eval_dataset(arguments.dataset)
    outcomes = (
        run_fixture_evaluation(dataset)
        if arguments.mode == "fixture"
        else run_provider_fixture_evaluation(dataset)
    )
    write_answer_eval_artifacts(
        outcomes,
        output_dir=arguments.output_dir,
        mode=arguments.mode,
    )


if __name__ == "__main__":
    _main()
