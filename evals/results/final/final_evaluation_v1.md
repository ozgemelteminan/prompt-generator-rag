# Final evaluation report

## Evidence classification

- **Real experimental/model results:** M4 benchmark artifacts below.
- **Deterministic fixture/harness validation:** M6 statuses below; these are not live-model quality scores.
- **Pending opt-in runs:** PostgreSQL/pgvector smoke, live answer-provider evaluation, and real operational timing.

## Selected production RAG architecture

StructureAwareChunker(350/500/40) → intfloat/multilingual-e5-large-instruct → PostgreSQL + pgvector dense retrieval → Context Builder → grounded generation → citation validation

Structure-aware chunking improved MRR from 0.844 to 0.899. E5 was the measured embedding MRR leader (0.870). Dense-only remains the default because Hybrid RRF added only a small ranking gain without recall gain or a recovered Dense miss; the tested reranker reduced Recall@5 and nDCG@10.

## M4 real experimental results

### Chunking

| Chunker | Recall@5 | Recall@10 | MRR | nDCG@10 |
| --- | ---: | ---: | ---: | ---: |
| fixed | 1.000 | 1.000 | 0.844 | 0.779 |
| recursive | 0.976 | 1.000 | 0.831 | 0.770 |
| production_structure_aware | 1.000 | 1.000 | 0.899 | 0.818 |

### Embeddings

| Model | Recall@10 | MRR | nDCG@10 | Block coverage@10 |
| --- | ---: | ---: | ---: | ---: |
| Alibaba-NLP/gte-multilingual-base | 0.970 | 0.802 | 0.790 | 0.970 |
| BAAI/bge-m3 | 0.982 | 0.828 | 0.812 | 0.982 |
| intfloat/multilingual-e5-large-instruct | 1.000 | 0.870 | 0.852 | 1.000 |
| ytu-ce-cosmos/turkish-e5-large | 0.988 | 0.817 | 0.807 | 0.988 |

### Dense, sparse, Hybrid, and Reranker ablation

| System | Recall@5 | Recall@10 | MRR | nDCG@10 | TR MRR | EN MRR |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Structure-aware + E5 Dense | 0.958 | 1.000 | 0.870 | 0.852 | 0.940 | 0.800 |
| Structure-aware + BM25 | 0.911 | 0.958 | 0.845 | 0.825 | 0.938 | 0.751 |
| Structure-aware + E5 Dense + BM25 + RRF | 0.958 | 1.000 | 0.877 | 0.857 | 0.962 | 0.793 |
| Dense + Reranker | 0.899 | 0.982 | 0.874 | 0.845 | 0.972 | 0.775 |
| Hybrid RRF + Reranker | 0.899 | 0.982 | 0.874 | 0.845 | 0.972 | 0.775 |

## M6 deterministic fixture/harness validation

| Area | Evidence kind | Status | Result |
| --- | --- | --- | --- |
| Production parity | deterministic harness | passed | 10/10 checks; pgvector smoke not_run |
| Answer/citation | fixture harness | fixture_only | Not a live-model quality result |
| Security | deterministic harness | deterministic_fixture_run | 10/10 cases |
| Operational | local fixture | completed | Real run not_run |

## Limitations

- M6 answer/citation scores are fixture-only unless an explicit provider run replaces that status.
- The pgvector smoke test is opt-in and remains unexecuted when its artifact status is not_run.
- M6 operational timings are local fixture measurements, not production latency targets.
- The current provider-neutral execution adapter exposes no real provider token/cost metadata.
- M6 security validation proves deterministic boundaries, not universal live-model prompt-injection robustness.
- The reviewed retrieval corpus contains 84 Turkish/English queries and is not representative production traffic.
