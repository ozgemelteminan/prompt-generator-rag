# M6.1 production RAG parity validation

Static parity status: **passed**.

## Checks

- PASS — `production_chunker_config`: StructureAwareChunker uses target/max/overlap 350/500/40.
- PASS — `embedding_model`: Production embedding provider uses the M4-selected multilingual E5 model.
- PASS — `e5_passage_format_and_normalization`: Passages are raw and normalized to 1024 dimensions.
- PASS — `e5_query_format_and_normalization`: Queries use the selected instructed E5 format and normalized vectors.
- PASS — `pgvector_cosine_hnsw_query`: PostgreSQL retrieval uses pgvector cosine distance with HNSW settings.
- PASS — `workspace_filter_before_results`: Workspace scope is a SQL filter before rows are ranked or returned.
- PASS — `production_context_builder`: Production ContextBuilder creates the cited ContextPackage source.
- PASS — `single_pass_grounded_ask`: A ready ask performs one retrieval and one generation.
- PASS — `insufficient_evidence_skips_generation`: Insufficient evidence produces no generation call.
- PASS — `citation_provenance_mapping`: Citation [1] maps only to the included production ContextPackage source.

## PostgreSQL + pgvector smoke

Status: **not_run** — Requires an explicitly provisioned PostgreSQL + pgvector database.

Run after applying migrations to an isolated smoke database:

```bash
RUN_PGVECTOR_SMOKE=1 PGVECTOR_SMOKE_DATABASE_URL=<postgresql+psycopg URL> PYTHONPATH=apps/api python -m pytest apps/api/tests/test_pgvector_smoke.py -q
```

## Limitations

- This is configuration and infrastructure parity validation, not answer-quality scoring.
- The default unit suite uses fake embeddings and generation; it does not download a model or call a provider.
- The PostgreSQL smoke test must run against a separately migrated pgvector database.
