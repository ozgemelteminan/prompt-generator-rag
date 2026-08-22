# Prompt Generator portfolio summary

Prompt Generator is a bilingual structured AI product that makes intent,
clarifications, and deterministic prompt compilation explicit, then extends the
same product with document-grounded answers and verifiable citations.

- Provider-independent PromptSpec and deterministic compiler separate user intent
  from model adapters and persistence.
- The prompt flow uses one semantic analysis call, up to four material
  clarifications, and optional separate execution.
- Production RAG uses structure-aware 350/500/40 chunking, multilingual E5,
  PostgreSQL + pgvector dense retrieval, bounded context, and citation validation.
- Real M4 evaluation selected E5 Dense (Recall@10 1.000; MRR 0.870; nDCG@10
  0.852) on an 84-query reviewed bilingual corpus.
- Hybrid RRF and one reranker were measured but kept out of production because
  their extra complexity did not justify the observed trade-offs.

Stack: Next.js, TypeScript, Tailwind CSS, FastAPI, Pydantic, SQLAlchemy,
Alembic, PostgreSQL/pgvector, and SentenceTransformers.

Limitations: the corpus is small; M6 answer/security/operational results are
deterministic harness evidence rather than universal live-model claims; real
pgvector smoke, live-provider answer evaluation, and production latency/cost
measurement remain opt-in work.
