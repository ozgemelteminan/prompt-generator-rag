"""enable pgvector extension

Revision ID: 202608210001
Revises:
Create Date: 2026-08-21 00:00:00

"""

from alembic import op

# revision identifiers, used by Alembic.
revision = "202608210001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")


def downgrade() -> None:
    op.execute("DROP EXTENSION IF EXISTS vector")
