"""Initial schema: provenance_records + jobs (matches backend/app/db/models.py).

Revision ID: 0001
Revises:
Create Date: 2026-07-06
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "provenance_records",
        sa.Column("record_id", sa.String(), primary_key=True),
        sa.Column("repo", sa.String(), nullable=False),
        sa.Column("commit_sha", sa.String(), nullable=False),
        sa.Column("file_path", sa.String(), nullable=False),
        sa.Column("line_start", sa.Integer(), nullable=False),
        sa.Column("line_end", sa.Integer(), nullable=False),
        sa.Column("author_type", sa.String(), nullable=False),
        sa.Column("model", sa.String(), nullable=True),
        sa.Column("agent", sa.String(), nullable=False),
        sa.Column("session_id", sa.String(), nullable=True),
        sa.Column("prompt_ref", sa.String(), nullable=True),
        sa.Column("prompt_redacted", sa.Text(), nullable=True),
        sa.Column("content", sa.Text(), nullable=True),
        sa.Column("human_edit_ratio", sa.Float(), nullable=False),
        sa.Column("reviewed_by", sa.String(), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("bound_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_provenance_records_repo", "provenance_records", ["repo"])
    op.create_index("ix_provenance_records_commit_sha", "provenance_records", ["commit_sha"])
    op.create_index("ix_provenance_records_file_path", "provenance_records", ["file_path"])

    op.create_table(
        "jobs",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("kind", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("repo", sa.String(), nullable=True),
        sa.Column("detail", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("jobs")
    op.drop_index("ix_provenance_records_file_path", table_name="provenance_records")
    op.drop_index("ix_provenance_records_commit_sha", table_name="provenance_records")
    op.drop_index("ix_provenance_records_repo", table_name="provenance_records")
    op.drop_table("provenance_records")
