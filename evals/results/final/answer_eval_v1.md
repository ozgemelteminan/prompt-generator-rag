# M6.2 answer, faithfulness, and citation evaluation

Execution status: **fixture_only** (fixture).

## Overall

| Metric | Score |
| --- | ---: |
| answer_correctness | 1.000 |
| citation_validity | 1.000 |
| citation_correctness | 1.000 |
| citation_completeness | 1.000 |
| faithfulness | 1.000 |
| insufficient_evidence_success | 1.000 |

## Failure examples

None in this run.

## Language, answerability, and category breakdown

| Group | Cases | Answer correctness | Citation validity | Citation correctness | Citation completeness | Faithfulness | Insufficient evidence |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| tr | 6 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 |
| en | 6 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 |
| answerable | 8 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 0.000 |
| unanswerable | 4 | 0.000 | 1.000 | 0.000 | 0.000 | 0.000 | 1.000 |
| architecture | 1 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 0.000 |
| cross_paragraph | 1 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 0.000 |
| factual | 2 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 0.000 |
| insufficient_evidence | 4 | 0.000 | 1.000 | 0.000 | 0.000 | 0.000 | 1.000 |
| provenance | 1 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 0.000 |
| safety | 2 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 0.000 |
| terminology | 1 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 0.000 |

## Limitations

- Fixture results validate the answer evaluation harness; they are not a real-provider answer-quality claim.
- Deterministic scoring covers only explicitly labeled facts and source blocks; it cannot detect every unsupported free-form claim.
- The fixture path uses reviewed source blocks, not a live PostgreSQL retrieval index. M6.1 separately covers production retrieval parity.

## Optional provider run

This uses the same reviewed fixture contexts and makes one configured-provider call for each answerable case; it does not replace the M6.1 PostgreSQL smoke test.

```bash
OPENAI_API_KEY=<key> PYTHONPATH=apps/api:packages/prompt-engine python -m evals.src.answer_eval --mode provider
```

