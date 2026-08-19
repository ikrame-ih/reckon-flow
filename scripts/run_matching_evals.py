"""Offline matching baselines on a synthetic dataset.

Run: uv run python scripts/run_matching_evals.py

Does not touch Postgres. The SQL prefilter is the same date-window +
amount-tolerance rules as ReconciliationService._prefilter.

Embeddings are the hashed-token stub in reckonflow.core.embeddings — not a
neural model. N is too small to claim production matching quality.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any, Literal

from rapidfuzz import fuzz, utils

from reckonflow.core.config import get_settings
from reckonflow.core.embeddings import text_embedding
from reckonflow.services.reconciliation import (
    amount_similarity,
    cosine_similarity,
    date_similarity,
    reciprocal_rank_fusion,
)

DATASET = Path(__file__).resolve().parents[1] / "evals" / "dataset" / "cases.json"
Baseline = Literal["fuzzy", "embeddings", "hybrid"]


@dataclass(frozen=True)
class Candidate:
    id: int
    description: str
    amount: Decimal
    booking_date: date


@dataclass(frozen=True)
class Case:
    id: str
    vendor: str
    description: str
    amount: Decimal
    expense_date: date
    gold_id: int
    candidates: tuple[Candidate, ...]

    @property
    def expense_text(self) -> str:
        return f"{self.vendor} {self.description}".strip()


def load_cases(path: Path = DATASET) -> list[Case]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    cases: list[Case] = []
    for raw in payload["cases"]:
        expense = raw["expense"]
        cases.append(
            Case(
                id=raw["id"],
                vendor=expense["vendor"],
                description=expense["description"],
                amount=Decimal(expense["amount"]),
                expense_date=date.fromisoformat(expense["date"]),
                gold_id=int(raw["gold_id"]),
                candidates=tuple(
                    Candidate(
                        id=int(row["id"]),
                        description=row["description"],
                        amount=Decimal(row["amount"]),
                        booking_date=date.fromisoformat(row["date"]),
                    )
                    for row in raw["candidates"]
                ),
            )
        )
    return cases


def _prefilter(
    case: Case, *, window: int, tolerance: float
) -> list[Candidate]:
    amount = abs(case.amount)
    slack = max(Decimal("0.01"), amount * Decimal(str(tolerance)))
    low, high = amount - slack, amount + slack
    kept: list[Candidate] = []
    for row in case.candidates:
        if abs((row.booking_date - case.expense_date).days) > window:
            continue
        magnitude = abs(row.amount)
        if not (low <= magnitude <= high):
            continue
        kept.append(row)
    return kept


def _fuzzy_score(case: Case, row: Candidate) -> float:
    return float(
        fuzz.token_set_ratio(
            case.expense_text,
            row.description,
            processor=utils.default_process,
        )
    )


def _embedding_score(case: Case, row: Candidate) -> float:
    return cosine_similarity(
        text_embedding(case.expense_text),
        text_embedding(row.description),
    )


def rank(case: Case, baseline: Baseline) -> list[int]:
    settings = get_settings()
    window = settings.reconciliation_date_window_days
    tolerance = settings.reconciliation_amount_tolerance
    filtered = _prefilter(case, window=window, tolerance=tolerance)
    if not filtered:
        return []

    if baseline == "fuzzy":
        ordered = sorted(
            filtered, key=lambda row: _fuzzy_score(case, row), reverse=True
        )
        return [row.id for row in ordered]

    if baseline == "embeddings":
        ordered = sorted(
            filtered, key=lambda row: _embedding_score(case, row), reverse=True
        )
        return [row.id for row in ordered]

    scored = [
        (
            row,
            _fuzzy_score(case, row),
            amount_similarity(case.amount, row.amount),
            date_similarity(
                case.expense_date, row.booking_date, window_days=window
            ),
            _embedding_score(case, row),
        )
        for row in filtered
    ]
    rankings: dict[str, list[int]] = {
        "fuzzy": [
            row.id
            for row, _fuzzy, *_rest in sorted(
                scored, key=lambda item: item[1], reverse=True
            )
        ],
        "amount_date": [
            row.id
            for row, _fuzzy, amount, day, _emb in sorted(
                scored, key=lambda item: (item[2] + item[3]) / 2, reverse=True
            )
        ],
        "embedding": [
            row.id
            for row, *_rest, _emb in sorted(
                scored, key=lambda item: item[4], reverse=True
            )
        ],
    }
    fused = reciprocal_rank_fusion(rankings, k=settings.reconciliation_rrf_k)
    return [
        candidate_id
        for candidate_id, _score in sorted(
            fused.items(), key=lambda item: item[1], reverse=True
        )
    ]


def evaluate(cases: list[Case] | None = None) -> dict[str, dict[str, Any]]:
    rows = cases if cases is not None else load_cases()
    report: dict[str, dict[str, Any]] = {}
    for baseline in ("fuzzy", "embeddings", "hybrid"):
        hit1 = 0
        hit3 = 0
        prefilter_miss = 0
        for case in rows:
            ranked = rank(case, baseline)
            if case.gold_id not in ranked:
                prefilter_miss += 1
                continue
            if ranked[0] == case.gold_id:
                hit1 += 1
            if case.gold_id in ranked[:3]:
                hit3 += 1
        n = len(rows)
        report[baseline] = {
            "n": n,
            "hit_at_1": hit1 / n if n else 0.0,
            "hit_at_3": hit3 / n if n else 0.0,
            "prefilter_dropped_gold": prefilter_miss,
            "hit_at_1_count": hit1,
            "hit_at_3_count": hit3,
        }
    return report


def _print_table(report: dict[str, dict[str, Any]]) -> None:
    print("Matching eval (synthetic). Stub embeddings. Do not cite as production.")
    print(
        f"{'baseline':<12} {'hit@1':>8} {'hit@3':>8} "
        f"{'gold dropped by prefilter':>28}"
    )
    for name, row in report.items():
        print(
            f"{name:<12} {row['hit_at_1']:>7.1%} {row['hit_at_3']:>7.1%} "
            f"{row['prefilter_dropped_gold']:>28}"
        )


def main() -> int:
    if not DATASET.is_file():
        print(f"Missing dataset: {DATASET}")
        return 1
    cases = load_cases()
    if not (30 <= len(cases) <= 50):
        print(f"Unexpected N={len(cases)}; expected 30–50 synthetic cases")
        return 1
    print(f"Dataset: {DATASET}  N={len(cases)}")
    print("Embeddings: hashed-token stub (reckonflow.core.embeddings)")
    _print_table(evaluate(cases))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
