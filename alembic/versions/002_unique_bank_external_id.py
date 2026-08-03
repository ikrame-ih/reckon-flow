"""Unique bank external_id to make CSV re-imports safe under concurrency

Revision ID: 002
Revises: 001
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "002_unique_bank_external_id"
down_revision: Union[str, None] = "001_initial"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_index("ix_bank_transactions_external_id", table_name="bank_transactions")
    # Partial unique: multiple NULL external_ids remain allowed
    op.create_index(
        "ix_bank_transactions_external_id",
        "bank_transactions",
        ["external_id"],
        unique=True,
        postgresql_where=sa.text("external_id IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("ix_bank_transactions_external_id", table_name="bank_transactions")
    op.create_index(
        "ix_bank_transactions_external_id",
        "bank_transactions",
        ["external_id"],
        unique=False,
    )
