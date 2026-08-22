# M6.4 RAG operational validation

## Deterministic/local latency

| Phase | Count | Mean ms | P50 ms | P95 ms |
| --- | ---: | ---: | ---: | ---: |
| query_embedding | 1 | 0.005 | 0.005 | 0.005 |
| retrieval | 1 | 2.166 | 2.166 | 2.166 |
| context_build | 1 | 0.034 | 0.034 | 0.034 |
| generation | 1 | 0.002 | 0.002 | 0.002 |
| total_ask | 1 | 2.237 | 2.237 | 2.237 |

## Request-count invariants

- Successful ask: {'query_embedding_calls': 1, 'retrieval_calls': 1, 'context_build_calls': 1, 'generation_calls': 1, 'passed': True}
- Insufficient evidence: {'query_embedding_calls': 1, 'retrieval_calls': 1, 'context_build_calls': 1, 'generation_calls': 0, 'passed': True}

## Operational checks

- `context_budget_bounded`: passed
- `retrieval_limit_bounded`: passed
- `timeout_configured`: passed
- `public_sources_exclude_vectors_and_storage`: passed
- `provider_failure_sanitized`: passed

## Token and cost accounting

{'input_tokens': None, 'output_tokens': None, 'total_tokens': None, 'generation_calls': 1, 'estimated_cost': None, 'currency': None, 'price_assumption': None}

## Real run

Status: **not_run**.

```bash
PYTHONPATH=apps/api:packages/prompt-engine python -m evals.src.operational_eval --mode real --query '<question>' --document-id '<embedded-document-id>'
```

Requirements: DATABASE_URL to migrated PostgreSQL + pgvector; embedded scoped document; OPENAI_API_KEY; local E5 model runtime.

## Limitations

- Local timings are deterministic-fixture measurements, not production latency targets.
- Current OpenAI execution results do not expose usage metadata through the provider-neutral adapter, so token totals and cost remain unavailable.
- No provider prices are hardcoded; an estimate requires an explicit external price assumption.
