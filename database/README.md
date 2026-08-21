# Database

M0 uses PostgreSQL with the pgvector image. The initial Alembic migration enables
the `vector` extension; it deliberately creates no application tables.

Run migrations from `apps/api` after starting PostgreSQL:

```bash
uv run alembic upgrade head
```
