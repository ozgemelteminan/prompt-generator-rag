# Deployment

Prompt Generator is deployed as a web container, API container, and PostgreSQL 16
container with pgvector. Alembic migrations are the only schema source of truth.
This guide is provider-neutral and does not perform an external deployment.

## Prerequisites

- Docker Engine with Compose v2
- A persistent volume provider for PostgreSQL and uploaded-document files
- An OpenAI API key supplied through your deployment secret manager
- Public HTTPS origins for the web application and API

Copy `.env.example` to `.env`, replace all `replace-with-...` values, and do
not commit `.env`. The template is deliberately deployment-oriented: its
database hostname is the Compose `postgres` service, and its public URLs are
examples that must be replaced.

Required settings are `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD`,
`DATABASE_URL`, `CORS_ORIGINS`, `OPENAI_API_KEY`, and
`NEXT_PUBLIC_API_BASE_URL`. Keep `APP_ENVIRONMENT=production` and
`DEBUG=false`. `CORS_ORIGINS` is a comma-separated explicit allow-list; `*` is
rejected. `NEXT_PUBLIC_API_BASE_URL` is compiled into the web build, so rebuild
the web image whenever it changes.

## Container startup

From the repository root:

```bash
cp .env.example .env
# edit .env with deployment values
docker compose up --build -d
```

Compose enforces the startup sequence:

```text
PostgreSQL + pgvector health check
→ alembic upgrade head
→ API health check
→ web
```

The database image provides pgvector; the first Alembic migration enables the
extension. Inspect migration output before promoting an image, and run the
migration job separately in orchestrated environments where Compose is not
used:

```bash
docker compose run --rm migrate
```

The API is exposed on `API_PORT` and the web application on `WEB_PORT`. The
API health endpoint is `GET /api/v1/health`.

## Persistent document storage

`document_data` is a named Docker volume mounted at `/app/data/uploads` for
the API. Back it with persistent storage and include it in backups alongside
`postgres_data`; losing it makes stored document metadata unusable. Local
filesystem storage is the current implementation. Object storage, replicated
storage, and a multi-instance shared-filesystem strategy are intentionally not
implemented yet.

## Post-deploy smoke checklist

1. Confirm `docker compose ps` shows a healthy PostgreSQL and API, and a running web container.
2. Request `https://api.example.com/api/v1/health` and verify the structured success response.
3. Open the web origin and verify browser requests use the configured public API origin without CORS errors.
4. Create a prompt, then verify rate-limit and quota errors remain friendly and do not expose provider data.
5. Upload a small supported document, prepare it, and ask a grounded question; verify citations map to displayed sources.
6. Verify a document cannot be read outside its workspace or explicit document selection.
7. Restart the API container and confirm uploaded documents remain available from the persistent mount.

## Security and operational notes

- Secrets come from environment variables or the deployment secret manager; no secrets belong in images or Git.
- Production rejects `DEBUG=true` and wildcard CORS origins. API exception handlers return stable sanitized errors.
- Upload type and size validation, workspace isolation, bounded retrieval/context limits, and private vectors/storage keys are unchanged.
- Current request rate limiting is process-local. Deploy one API replica unless an external shared limiter is introduced in a later milestone.
- This repository does not include TLS termination, authentication provisioning, object storage, backups, monitoring, or external deployment automation. Provide those at the hosting boundary before a public launch.
