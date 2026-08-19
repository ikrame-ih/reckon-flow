"""Record extraction attempts after the HTTP 202

Revision ID: 005
Revises: 004
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "005_extraction_runs"
down_revision: Union[str, None] = "004_ledger_immutable"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "extraction_runs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "receipt_id",
            sa.Integer(),
            sa.ForeignKey("receipts.id"),
            nullable=False,
        ),
        sa.Column("provider", sa.String(64), nullable=False),
        sa.Column("outcome", sa.String(32), nullable=False),
        sa.Column("duration_ms", sa.Integer(), nullable=False),
        sa.Column("attempt", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("job_id", sa.String(128), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("token_count", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_extraction_runs_receipt_id", "extraction_runs", ["receipt_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_extraction_runs_receipt_id", table_name="extraction_runs")
    op.drop_table("extraction_runs")
