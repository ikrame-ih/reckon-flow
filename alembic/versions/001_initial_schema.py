"""Initial schema: ledger, travel domain, receipts, bank lines

Revision ID: 001_initial
Revises:
Create Date: 2026-08-03
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "001_initial"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # No CREATE EXTENSION vector — stock Windows PostgreSQL works; embeddings in JSONB

    op.create_table(
        "accounts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("code", sa.String(32), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False, server_default="EUR"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.UniqueConstraint("code"),
    )
    op.create_index("ix_accounts_code", "accounts", ["code"])

    op.create_table(
        "ledger_transactions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("reference", sa.String(64), nullable=False),
        sa.Column("description", sa.String(255), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.UniqueConstraint("reference"),
    )
    op.create_index("ix_ledger_transactions_reference", "ledger_transactions", ["reference"])

    op.create_table(
        "ledger_entries",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "transaction_id",
            sa.Integer(),
            sa.ForeignKey("ledger_transactions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "account_id", sa.Integer(), sa.ForeignKey("accounts.id"), nullable=False
        ),
        sa.Column("debit", sa.Numeric(15, 4), nullable=False, server_default="0"),
        sa.Column("credit", sa.Numeric(15, 4), nullable=False, server_default="0"),
        sa.Column("currency", sa.String(3), nullable=False, server_default="EUR"),
        sa.Column("memo", sa.Text(), nullable=True),
        sa.CheckConstraint(
            "(debit > 0 AND credit = 0) OR (credit > 0 AND debit = 0)",
            name="ck_ledger_entry_one_sided",
        ),
        sa.CheckConstraint(
            "debit >= 0 AND credit >= 0", name="ck_ledger_entry_nonneg"
        ),
    )
    op.create_index(
        "ix_ledger_entries_transaction_id", "ledger_entries", ["transaction_id"]
    )
    op.create_index("ix_ledger_entries_account_id", "ledger_entries", ["account_id"])

    # Deferred constraint trigger — multi-row inserts finish before balance check
    op.execute(
        """
        CREATE OR REPLACE FUNCTION check_ledger_transaction_balanced()
        RETURNS trigger AS $$
        DECLARE
            imbalance NUMERIC(15, 4);
        BEGIN
            SELECT COALESCE(SUM(debit), 0) - COALESCE(SUM(credit), 0)
            INTO imbalance
            FROM ledger_entries
            WHERE transaction_id = COALESCE(NEW.transaction_id, OLD.transaction_id);

            IF imbalance <> 0 THEN
                RAISE EXCEPTION
                    'Unbalanced ledger transaction % (imbalance %)',
                    COALESCE(NEW.transaction_id, OLD.transaction_id), imbalance;
            END IF;
            RETURN NULL;
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    op.execute(
        """
        CREATE CONSTRAINT TRIGGER trg_ledger_tx_balanced
        AFTER INSERT OR UPDATE OR DELETE ON ledger_entries
        DEFERRABLE INITIALLY DEFERRED
        FOR EACH ROW
        EXECUTE FUNCTION check_ledger_transaction_balanced();
        """
    )

    op.create_table(
        "travel_requests",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("employee_name", sa.String(120), nullable=False),
        sa.Column("destination", sa.String(120), nullable=False),
        sa.Column("purpose", sa.Text(), nullable=False),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=False),
        sa.Column("estimated_amount", sa.Numeric(15, 4), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False, server_default="EUR"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )

    op.create_table(
        "approvals",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "travel_request_id",
            sa.Integer(),
            sa.ForeignKey("travel_requests.id"),
            nullable=False,
            unique=True,
        ),
        sa.Column("status", sa.String(32), nullable=False, server_default="pending"),
        sa.Column("reviewer", sa.String(120), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )

    op.create_table(
        "expenses",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "travel_request_id",
            sa.Integer(),
            sa.ForeignKey("travel_requests.id"),
            nullable=True,
        ),
        sa.Column("vendor", sa.String(160), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("amount", sa.Numeric(15, 4), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False, server_default="EUR"),
        sa.Column("expense_date", sa.Date(), nullable=False),
        sa.Column(
            "match_status", sa.String(32), nullable=False, server_default="unmatched"
        ),
        sa.Column("embedding", sa.JSON(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index("ix_expenses_travel_request_id", "expenses", ["travel_request_id"])

    op.create_table(
        "receipts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "expense_id",
            sa.Integer(),
            sa.ForeignKey("expenses.id"),
            nullable=True,
            unique=True,
        ),
        sa.Column("filename", sa.String(255), nullable=False),
        sa.Column("content_type", sa.String(120), nullable=False),
        sa.Column("storage_path", sa.String(512), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="uploaded"),
        sa.Column("extracted_json", sa.Text(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )

    op.create_table(
        "bank_transactions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("booking_date", sa.Date(), nullable=False),
        sa.Column("amount", sa.Numeric(15, 4), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False, server_default="EUR"),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("external_id", sa.String(64), nullable=True),
        sa.Column(
            "match_status", sa.String(32), nullable=False, server_default="unmatched"
        ),
        sa.Column(
            "matched_expense_id",
            sa.Integer(),
            sa.ForeignKey("expenses.id"),
            nullable=True,
            unique=True,
        ),
        sa.Column("embedding", sa.JSON(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_bank_transactions_booking_date", "bank_transactions", ["booking_date"]
    )
    op.create_index(
        "ix_bank_transactions_external_id", "bank_transactions", ["external_id"]
    )


def downgrade() -> None:
    op.drop_table("bank_transactions")
    op.drop_table("receipts")
    op.drop_table("expenses")
    op.drop_table("approvals")
    op.drop_table("travel_requests")
    op.execute("DROP TRIGGER IF EXISTS trg_ledger_tx_balanced ON ledger_entries")
    op.execute("DROP FUNCTION IF EXISTS check_ledger_transaction_balanced")
    op.drop_table("ledger_entries")
    op.drop_table("ledger_transactions")
    op.drop_table("accounts")
