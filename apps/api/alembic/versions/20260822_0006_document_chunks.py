"""add structure-aware document chunks

Revision ID: 202608220006
Revises: 202608220005
Create Date: 2026-08-22 01:00:00

"""

import sqlalchemy as sa

from alembic import op

revision = "202608220006"
down_revision = "202608220005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint("ck_documents_ingestion_status", "documents", type_="check")
    op.create_check_constraint(
        "ck_documents_ingestion_status",
        "documents",
        (
            "ingestion_status IN ('uploaded', 'processing', 'parsed', 'chunking', "
            "'chunked', 'ready', 'failed')"
        ),
    )
    op.create_table(
        "document_chunks",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("workspace_id", sa.String(length=128), nullable=False),
        sa.Column("document_id", sa.String(length=36), nullable=False),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("token_count", sa.Integer(), nullable=False),
        sa.Column("language", sa.String(length=8), nullable=True),
        sa.Column("page_start", sa.Integer(), nullable=True),
        sa.Column("page_end", sa.Integer(), nullable=True),
        sa.Column("section", sa.Text(), nullable=True),
        sa.Column("heading", sa.Text(), nullable=True),
        sa.Column("source_block_start", sa.Integer(), nullable=False),
        sa.Column("source_block_end", sa.Integer(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("chunk_index >= 0", name="ck_document_chunks_nonnegative_index"),
        sa.CheckConstraint("token_count > 0", name="ck_document_chunks_positive_token_count"),
        sa.ForeignKeyConstraint(["document_id"], ["documents.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("document_id", "chunk_index", name="uq_document_chunks_document_index"),
    )
    op.create_index("ix_document_chunks_workspace_id", "document_chunks", ["workspace_id"])
    op.create_index("ix_document_chunks_document_id", "document_chunks", ["document_id"])


def downgrade() -> None:
    op.drop_index("ix_document_chunks_document_id", table_name="document_chunks")
    op.drop_index("ix_document_chunks_workspace_id", table_name="document_chunks")
    op.drop_table("document_chunks")
    op.drop_constraint("ck_documents_ingestion_status", "documents", type_="check")
    op.create_check_constraint(
        "ck_documents_ingestion_status",
        "documents",
        "ingestion_status IN ('uploaded', 'processing', 'parsed', 'ready', 'failed')",
    )
