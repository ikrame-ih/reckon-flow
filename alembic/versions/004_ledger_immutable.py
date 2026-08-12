"""Money CHECKs + append-only ledger triggers

Revision ID: 004
Revises: 003
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op

# Keep <= 32 chars — alembic_version.version_num is VARCHAR(32)
revision: str = "004_ledger_immutable"
down_revision: Union[str, None] = "003_ledger_fk_restrict"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE travel_requests
        ADD CONSTRAINT ck_travel_requests_estimated_amount_positive
        CHECK (estimated_amount > 0)
        """
    )
    op.execute(
        """
        ALTER TABLE expenses
        ADD CONSTRAINT ck_expenses_amount_positive
        CHECK (amount > 0)
        """
    )

    op.execute(
        """
        CREATE OR REPLACE FUNCTION refuse_ledger_mutation()
        RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION
                'ledger is append-only: % on % is not allowed; post a reversing transaction',
                TG_OP, TG_TABLE_NAME
                USING ERRCODE = 'integrity_constraint_violation';
            RETURN NULL;
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_ledger_transactions_immutable
        BEFORE UPDATE OR DELETE ON ledger_transactions
        FOR EACH ROW EXECUTE FUNCTION refuse_ledger_mutation();
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_ledger_entries_immutable
        BEFORE UPDATE OR DELETE ON ledger_entries
        FOR EACH ROW EXECUTE FUNCTION refuse_ledger_mutation();
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_ledger_entries_immutable ON ledger_entries")
    op.execute(
        "DROP TRIGGER IF EXISTS trg_ledger_transactions_immutable ON ledger_transactions"
    )
    op.execute("DROP FUNCTION IF EXISTS refuse_ledger_mutation()")
    op.execute(
        "ALTER TABLE expenses DROP CONSTRAINT IF EXISTS ck_expenses_amount_positive"
    )
    op.execute(
        "ALTER TABLE travel_requests "
        "DROP CONSTRAINT IF EXISTS ck_travel_requests_estimated_amount_positive"
    )
