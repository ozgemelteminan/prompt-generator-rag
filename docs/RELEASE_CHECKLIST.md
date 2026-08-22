# Release checklist

Use this checklist immediately before the first release commit and optional
`v1.0.0` Git tag. The tag is a recommendation only; this repository does not
create or push it automatically.

## Repository and documentation

- [ ] `git status --short` is clean after staging the intended release files.
- [ ] No `.env`, secrets, uploads, database files, caches, `.next`, or
  `*.tsbuildinfo` files are tracked.
- [ ] README, demo, architecture, deployment, portfolio, and final evaluation
  links resolve.
- [ ] Product positioning remains: structured AI Prompt Generator first;
  document intelligence/RAG is the advanced subsystem.

## Verification and deployment readiness

- [ ] API, Prompt Engine, evaluation, and frontend checks are green.
- [ ] Alembic migrations apply to the intended PostgreSQL + pgvector database.
- [ ] `docker compose config` validates with deployment environment values.
- [ ] Production uses explicit CORS origins, `DEBUG=false`, secret-managed keys,
  and persistent PostgreSQL/document-storage volumes.
- [ ] Health endpoint and post-deploy smoke checklist in `DEPLOYMENT.md` pass.

## Pending opt-in validation before a public demo or production launch

- [ ] Run the real PostgreSQL + pgvector smoke test.
- [ ] Run the live-provider RAG answer-quality evaluation.
- [ ] Measure real E5/provider latency and token/cost metadata.
- [ ] Capture and privacy-review real product screenshots listed in
  `docs/screenshots/README.md`.

Current operational limitations remain intentional: local filesystem document
storage requires a persistent mount, and process-local rate limiting requires a
single API replica until a shared limiter is introduced.
