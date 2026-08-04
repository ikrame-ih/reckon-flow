"""Restrict ledger entry deletes — append-only means no cascading wipe

Revision ID: 003
Revises: 002
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "003_ledger_fk_restrict"
down_revision: Union[str, None] = "002_unique_bank_external_id"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_constraint(
        "ledger_entries_transaction_id_fkey",
        "ledger_entries",
        type_="foreignkey",
    )
    op.create_foreign_key(
        "ledger_entries_transaction_id_fkey",
        "ledger_entries",
        "ledger_transactions",
        ["transaction_id"],
        ["id"],
        ondelete="RESTRICT",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ledger_entries_transaction_id_fkey",
        "ledger_entries",
        type_="foreignkey",
    )
    op.create_foreign_key(
        "ledger_entries_transaction_id_fkey",
        "ledger_entries",
        "ledger_transactions",
        ["transaction_id"],
        ["id"],
        ondelete="CASCADE",
    )
