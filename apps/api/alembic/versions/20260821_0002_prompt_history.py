"""add prompt history tables

Revision ID: 202608210002
Revises: 202608210001
Create Date: 2026-08-21 00:00:00

"""

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = "202608210002"
down_revision = "202608210001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "prompt_generations",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("owner_id", sa.String(length=128), nullable=True),
        sa.Column("original_input", sa.Text(), nullable=False),
        sa.Column("language", sa.String(length=2), nullable=False),
        sa.Column("preset_id", sa.String(length=64), nullable=True),
        sa.Column("prompt_spec", sa.JSON(), nullable=False),
        sa.Column("generation_state", sa.String(length=32), nullable=False),
        sa.Column("compiled_prompt", sa.Text(), nullable=False),
        sa.Column("is_favorite", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_prompt_generations_owner_id", "prompt_generations", ["owner_id"])
    op.create_table(
        "prompt_executions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("prompt_id", sa.String(length=36), nullable=False),
        sa.Column("output", sa.Text(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["prompt_id"], ["prompt_generations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_prompt_executions_prompt_id", "prompt_executions", ["prompt_id"])
    op.create_table(
        "prompt_feedback",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("prompt_id", sa.String(length=36), nullable=False),
        sa.Column("execution_id", sa.String(length=36), nullable=True),
        sa.Column("rating", sa.String(length=16), nullable=False),
        sa.Column("reason", sa.String(length=80), nullable=True),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("rating IN ('positive', 'negative')", name="ck_prompt_feedback_rating"),
        sa.ForeignKeyConstraint(["execution_id"], ["prompt_executions.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["prompt_id"], ["prompt_generations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_prompt_feedback_prompt_id", "prompt_feedback", ["prompt_id"])
    op.create_index("ix_prompt_feedback_execution_id", "prompt_feedback", ["execution_id"])


def downgrade() -> None:
    op.drop_index("ix_prompt_feedback_execution_id", table_name="prompt_feedback")
    op.drop_index("ix_prompt_feedback_prompt_id", table_name="prompt_feedback")
    op.drop_table("prompt_feedback")
    op.drop_index("ix_prompt_executions_prompt_id", table_name="prompt_executions")
    op.drop_table("prompt_executions")
    op.drop_index("ix_prompt_generations_owner_id", table_name="prompt_generations")
    op.drop_table("prompt_generations")
