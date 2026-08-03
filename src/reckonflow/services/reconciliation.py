"""I match expenses to bank lines with a small hybrid retrieval pipeline

The problem: "TAXI BERLIN 14/09" on a card statement and "Airport transfer,
Berlin" in an expense form are the same payment, but no exact join finds them

The pipeline, cheapest stage first:

1. **SQL prefilter** — only bank rows inside a date window and an amount
   tolerance survive. This is the stage that makes the rest affordable: fuzzy
   matching every expense against a full statement is O(n*m)
2. **RapidFuzz** on descriptions — catches abbreviations and reordered words
3. **Embedding cosine**, only when both rows already have an embedding —
   catches wording that shares no tokens at all
4. **Reciprocal Rank Fusion (k=60)** — I fuse the *rankings*, not the scores

Why RRF rather than a weighted sum: the signals are not comparable. RapidFuzz
returns 0-100, cosine returns -1 to 1, and amount closeness is its own scale.
Normalising them into one weighted score means inventing weights I cannot
defend. RRF only needs each signal to order candidates sensibly, so a signal
being absent (no embeddings) degrades the result instead of breaking it

Above the confidence threshold I auto-match; below it the pair goes to
`pending_review`. Silence is the failure mode I want in accounting — an
unreviewed wrong match is far more expensive than a queue item
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal

from rapidfuzz import fuzz, utils
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from reckonflow.core.config import get_settings
from reckonflow.core.exceptions import ConflictError, NotFoundError
from reckonflow.models import BankTransaction, Expense
from reckonflow.models.travel import MatchStatus

# I only consider bank rows that are still available to be claimed
_OPEN_STATUSES = (
    MatchStatus.UNMATCHED.value,
    MatchStatus.SUGGESTED.value,
    MatchStatus.PENDING_REVIEW.value,
)


def reciprocal_rank_fusion(
    rankings: Mapping[str, Sequence[int]], *, k: int = 60
) -> dict[int, float]:
    """I fuse ranked candidate lists into one score per candidate

    score(d) = sum over rankings of 1 / (k + rank(d)), ranks starting at 1

    k = 60 is the value from the original RRF paper. It flattens the curve so
    rank 1 does not dominate rank 2, which matters here: my signals disagree
    about the ordering more often than they disagree about the shortlist
    """
    if k <= 0:
        raise ValueError("RRF k must be positive")

    fused: dict[int, float] = {}
    for ranked_ids in rankings.values():
        for position, candidate_id in enumerate(ranked_ids, start=1):
            fused[candidate_id] = fused.get(candidate_id, 0.0) + 1.0 / (k + position)
    return fused


def max_rrf_score(ranking_count: int, *, k: int = 60) -> float:
    """I return the best score reachable: first place in every ranking

    Dividing by this turns a raw RRF score into a 0-1 confidence, which is
    what makes a single configured threshold meaningful across runs where a
    different number of signals was available
    """
    if ranking_count <= 0:
        return 0.0
    return ranking_count / (k + 1)


def cosine_similarity(left: Sequence[float], right: Sequence[float]) -> float:
    """I return cosine similarity, or 0.0 when either vector is unusable"""
    if not left or not right or len(left) != len(right):
        return 0.0
    dot = sum(a * b for a, b in zip(left, right, strict=True))
    norm_left = math.sqrt(sum(a * a for a in left))
    norm_right = math.sqrt(sum(b * b for b in right))
    if norm_left == 0.0 or norm_right == 0.0:
        return 0.0
    return dot / (norm_left * norm_right)


def amount_similarity(left: Decimal, right: Decimal) -> float:
    """I score how close two amounts are, 1.0 when identical

    I compare magnitudes because a statement may sign an expense negatively
    while the expense form stores it positive
    """
    a, b = abs(left), abs(right)
    largest = max(a, b)
    if largest == 0:
        return 1.0
    return float(1 - (abs(a - b) / largest))


def date_similarity(left: date, right: date, *, window_days: int) -> float:
    """I score date closeness linearly across the allowed window"""
    if window_days <= 0:
        return 1.0 if left == right else 0.0
    distance = abs((left - right).days)
    return max(0.0, 1.0 - distance / window_days)


@dataclass(frozen=True)
class ScoredCandidate:
    """I hold one bank row plus every signal computed for it"""

    bank_transaction: BankTransaction
    fuzzy_score: float
    amount_score: float
    date_score: float
    embedding_score: float | None = None
    rrf_score: float = 0.0
    confidence: float = 0.0
    auto_matchable: bool = False
    rankings_used: tuple[str, ...] = field(default=())


class ReconciliationService:
    """I produce match suggestions and commit confirmed matches safely"""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._settings = get_settings()

    async def suggest_matches(
        self,
        expense_id: int,
        *,
        limit: int = 5,
        date_window_days: int | None = None,
        amount_tolerance: float | None = None,
    ) -> tuple[Expense, list[ScoredCandidate], int]:
        """I return the expense, its ranked candidates, and the prefilter size"""
        expense = await self._session.get(Expense, expense_id)
        if expense is None:
            raise NotFoundError(f"Expense {expense_id} not found")

        window = (
            date_window_days
            if date_window_days is not None
            else self._settings.reconciliation_date_window_days
        )
        tolerance = (
            amount_tolerance
            if amount_tolerance is not None
            else self._settings.reconciliation_amount_tolerance
        )

        candidates = await self._prefilter(expense, window=window, tolerance=tolerance)
        if not candidates:
            return expense, [], 0

        scored = self._score(expense, candidates, window=window)
        ranked = self._fuse(scored, limit=limit)
        return expense, ranked, len(candidates)

    async def _prefilter(
        self, expense: Expense, *, window: int, tolerance: float
    ) -> list[BankTransaction]:
        """I let the database throw away everything that cannot possibly match

        The index on booking_date does the heavy lifting; without this stage
        every suggestion would fuzzy-compare against the whole statement
        """
        amount = abs(Decimal(expense.amount))
        # I keep an absolute floor so tiny amounts still tolerate a cent of
        # rounding, and scale with the amount for larger ones
        slack = max(Decimal("0.01"), amount * Decimal(str(tolerance)))
        low, high = amount - slack, amount + slack

        stmt = (
            select(BankTransaction)
            .where(
                BankTransaction.matched_expense_id.is_(None),
                BankTransaction.match_status.in_(_OPEN_STATUSES),
                BankTransaction.booking_date.between(
                    expense.expense_date - timedelta(days=window),
                    expense.expense_date + timedelta(days=window),
                ),
                or_(
                    BankTransaction.amount.between(low, high),
                    BankTransaction.amount.between(-high, -low),
                ),
            )
            .order_by(BankTransaction.booking_date)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    def _score(
        self, expense: Expense, candidates: list[BankTransaction], *, window: int
    ) -> list[ScoredCandidate]:
        """I compute every available signal for each surviving candidate"""
        expense_text = f"{expense.vendor} {expense.description}".strip()
        expense_amount = Decimal(expense.amount)
        expense_embedding = expense.embedding

        scored: list[ScoredCandidate] = []
        for candidate in candidates:
            embedding_score: float | None = None
            if expense_embedding and candidate.embedding:
                embedding_score = cosine_similarity(
                    expense_embedding, candidate.embedding
                )
            scored.append(
                ScoredCandidate(
                    bank_transaction=candidate,
                    # token_set_ratio ignores word order and duplicated tokens,
                    # which is exactly how bank descriptions differ from forms
                    # default_process lowercases and strips punctuation, without
                    # which "HOTEL ADLON" would not match "Hotel Adlon" at all
                    fuzzy_score=float(
                        fuzz.token_set_ratio(
                            expense_text,
                            candidate.description,
                            processor=utils.default_process,
                        )
                    ),
                    amount_score=amount_similarity(
                        expense_amount, Decimal(candidate.amount)
                    ),
                    date_score=date_similarity(
                        expense.expense_date,
                        candidate.booking_date,
                        window_days=window,
                    ),
                    embedding_score=embedding_score,
                )
            )
        return scored

    def _fuse(
        self, scored: list[ScoredCandidate], *, limit: int
    ) -> list[ScoredCandidate]:
        """I rank by each signal, fuse the ranks, and gate the auto-match"""
        by_id = {item.bank_transaction.id: item for item in scored}

        rankings: dict[str, list[int]] = {
            "fuzzy": [
                item.bank_transaction.id
                for item in sorted(scored, key=lambda i: i.fuzzy_score, reverse=True)
            ],
            # Amount and date are one ranking: on a statement they are the two
            # halves of the same "is this the same payment" question
            "amount_date": [
                item.bank_transaction.id
                for item in sorted(
                    scored,
                    key=lambda i: (i.amount_score + i.date_score) / 2,
                    reverse=True,
                )
            ],
        }
        if any(item.embedding_score is not None for item in scored):
            rankings["embedding"] = [
                item.bank_transaction.id
                for item in sorted(
                    scored,
                    key=lambda i: i.embedding_score or -1.0,
                    reverse=True,
                )
            ]

        k = self._settings.reconciliation_rrf_k
        fused = reciprocal_rank_fusion(rankings, k=k)
        best_possible = max_rrf_score(len(rankings), k=k) or 1.0
        threshold = self._settings.reconciliation_auto_match_threshold
        min_fuzzy = self._settings.reconciliation_min_fuzzy_score

        results: list[ScoredCandidate] = []
        for candidate_id, raw_score in fused.items():
            item = by_id[candidate_id]
            confidence = min(1.0, raw_score / best_possible)
            results.append(
                ScoredCandidate(
                    bank_transaction=item.bank_transaction,
                    fuzzy_score=item.fuzzy_score,
                    amount_score=item.amount_score,
                    date_score=item.date_score,
                    embedding_score=item.embedding_score,
                    rrf_score=raw_score,
                    confidence=confidence,
                    # Rank alone is not evidence: with two candidates, one of
                    # them is always first. I also require the text to agree
                    auto_matchable=(
                        confidence >= threshold and item.fuzzy_score >= min_fuzzy
                    ),
                    rankings_used=tuple(rankings),
                )
            )

        results.sort(key=lambda i: (i.confidence, i.fuzzy_score), reverse=True)
        return results[:limit]

    async def confirm_match(
        self, expense_id: int, bank_transaction_id: int
    ) -> tuple[Expense, BankTransaction]:
        """I link an expense to a bank line under a row lock

        Two reviewers can open the same suggestion. Without a lock both could
        read "unmatched", both write, and one payment ends up reconciled
        twice. I take `SELECT ... FOR UPDATE` on both rows in a fixed order
        (expense first) so concurrent confirmations serialize instead of
        deadlocking, and re-check the state *after* acquiring the lock
        """
        lock = self._supports_row_locks()

        expense_stmt = select(Expense).where(Expense.id == expense_id)
        if lock:
            expense_stmt = expense_stmt.with_for_update()
        expense = (await self._session.execute(expense_stmt)).scalar_one_or_none()
        if expense is None:
            raise NotFoundError(f"Expense {expense_id} not found")

        bank_stmt = select(BankTransaction).where(
            BankTransaction.id == bank_transaction_id
        )
        if lock:
            bank_stmt = bank_stmt.with_for_update()
        bank_row = (await self._session.execute(bank_stmt)).scalar_one_or_none()
        if bank_row is None:
            raise NotFoundError(f"Bank transaction {bank_transaction_id} not found")

        if bank_row.matched_expense_id not in (None, expense_id):
            raise ConflictError(
                f"Bank transaction {bank_transaction_id} is already matched to "
                f"expense {bank_row.matched_expense_id}"
            )
        if expense.match_status == MatchStatus.MATCHED.value:
            raise ConflictError(f"Expense {expense_id} is already matched")

        bank_row.matched_expense_id = expense_id
        bank_row.match_status = MatchStatus.MATCHED
        expense.match_status = MatchStatus.MATCHED
        await self._session.flush()
        return expense, bank_row

    async def flag_for_review(self, expense_id: int) -> Expense:
        """I park an expense in the reviewer queue when no candidate is safe"""
        expense = await self._session.get(Expense, expense_id)
        if expense is None:
            raise NotFoundError(f"Expense {expense_id} not found")
        expense.match_status = MatchStatus.PENDING_REVIEW
        await self._session.flush()
        return expense

    async def auto_reconcile(self, expense_id: int) -> tuple[Expense, int | None]:
        """I match automatically when the top candidate clears every gate

        Returns the expense and the bank row it claimed, or None when the case
        was parked for a human
        """
        expense, ranked, _ = await self.suggest_matches(expense_id, limit=2)
        if not ranked:
            return await self.flag_for_review(expense_id), None

        best = ranked[0]
        if not best.auto_matchable:
            return await self.flag_for_review(expense_id), None

        # If the runner-up also clears every gate, the evidence does not
        # distinguish them and picking one would be a coin flip dressed up as
        # a decision. I compare on the gates rather than on the score gap:
        # the RRF distance between adjacent ranks is fixed by k, so it says
        # nothing about how much better the winner actually is
        if len(ranked) > 1 and ranked[1].auto_matchable:
            return await self.flag_for_review(expense_id), None

        matched_expense, bank_row = await self.confirm_match(
            expense_id, best.bank_transaction.id
        )
        return matched_expense, bank_row.id

    def _supports_row_locks(self) -> bool:
        """I only emit FOR UPDATE where the dialect implements it

        SQLite is my unit-test database and would reject the clause outright
        """
        try:
            return self._session.get_bind().dialect.name in {
                "postgresql",
                "mysql",
                "oracle",
            }
        except Exception:
            return False
