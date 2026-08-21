"""add parsed document blocks

Revision ID: 202608220005
Revises: 202608220004
Create Date: 2026-08-22 00:30:00

"""

import sqlalchemy as sa

from alembic import op

revision = "202608220005"
down_revision = "202608220004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint("ck_documents_ingestion_status", "documents", type_="check")
    op.create_check_constraint(
        "ck_documents_ingestion_status",
        "documents",
        "ingestion_status IN ('uploaded', 'processing', 'parsed', 'ready', 'failed')",
    )
    op.create_table(
        "document_blocks",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("document_id", sa.String(length=36), nullable=False),
        sa.Column("order_index", sa.Integer(), nullable=False),
        sa.Column("block_type", sa.String(length=32), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("page_number", sa.Integer(), nullable=True),
        sa.Column("heading_level", sa.Integer(), nullable=True),
        sa.Column("section", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("order_index >= 0", name="ck_document_blocks_nonnegative_order"),
        sa.ForeignKeyConstraint(["document_id"], ["documents.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("document_id", "order_index", name="uq_document_blocks_document_order"),
    )
    op.create_index("ix_document_blocks_document_id", "document_blocks", ["document_id"])


def downgrade() -> None:
    op.drop_index("ix_document_blocks_document_id", table_name="document_blocks")
    op.drop_table("document_blocks")
    op.drop_constraint("ck_documents_ingestion_status", "documents", type_="check")
    op.create_check_constraint(
        "ck_documents_ingestion_status",
        "documents",
        "ingestion_status IN ('uploaded', 'processing', 'ready', 'failed')",
    )
