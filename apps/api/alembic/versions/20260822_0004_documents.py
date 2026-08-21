"""add document upload foundation

Revision ID: 202608220004
Revises: 202608210003
Create Date: 2026-08-22 00:00:00

"""

import sqlalchemy as sa

from alembic import op

revision = "202608220004"
down_revision = "202608210003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "documents",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("workspace_id", sa.String(length=128), nullable=False),
        sa.Column("original_filename", sa.String(length=255), nullable=False),
        sa.Column("media_type", sa.String(length=128), nullable=False),
        sa.Column("file_size", sa.BigInteger(), nullable=False),
        sa.Column("checksum", sa.String(length=64), nullable=False),
        sa.Column("language", sa.String(length=8), nullable=True),
        sa.Column("ingestion_status", sa.String(length=16), nullable=False),
        sa.Column("storage_key", sa.String(length=512), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("file_size > 0", name="ck_documents_positive_file_size"),
        sa.CheckConstraint(
            "ingestion_status IN ('uploaded', 'processing', 'ready', 'failed')",
            name="ck_documents_ingestion_status",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("workspace_id", "checksum", name="uq_documents_workspace_checksum"),
        sa.UniqueConstraint("storage_key"),
    )
    op.create_index("ix_documents_workspace_id", "documents", ["workspace_id"])
    op.create_index("ix_documents_ingestion_status", "documents", ["ingestion_status"])


def downgrade() -> None:
    op.drop_index("ix_documents_ingestion_status", table_name="documents")
    op.drop_index("ix_documents_workspace_id", table_name="documents")
    op.drop_table("documents")
