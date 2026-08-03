"""I test the fusion maths on its own, with no database and no ORM

Reciprocal Rank Fusion is the piece I most need to be able to reason about:
if the ranking arithmetic is wrong, every suggestion is subtly wrong and no
integration test would tell me why
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from reckonflow.services.reconciliation import (
    amount_similarity,
    cosine_similarity,
    date_similarity,
    max_rrf_score,
    reciprocal_rank_fusion,
)


def test_rrf_scores_follow_the_formula() -> None:
    fused = reciprocal_rank_fusion({"fuzzy": [7, 3]}, k=60)

    assert fused[7] == pytest.approx(1 / 61)
    assert fused[3] == pytest.approx(1 / 62)


def test_rrf_sums_across_rankings() -> None:
    fused = reciprocal_rank_fusion({"fuzzy": [1, 2], "amount": [2, 1]}, k=60)

    # Both candidates take one first place and one second, so they tie
    assert fused[1] == pytest.approx(fused[2])
    assert fused[1] == pytest.approx(1 / 61 + 1 / 62)


def test_rrf_rewards_agreement_between_signals() -> None:
    """The candidate every signal likes must beat the one only some like"""
    fused = reciprocal_rank_fusion(
        {"fuzzy": [1, 2, 3], "amount": [1, 3, 2], "embedding": [1, 2, 3]}, k=60
    )

    assert fused[1] > fused[2] > fused[3]


def test_rrf_tolerates_a_missing_signal() -> None:
    """A candidate absent from one ranking still scores from the others

    This is the property that lets embeddings be optional
    """
    fused = reciprocal_rank_fusion({"fuzzy": [1, 2], "embedding": [1]}, k=60)

    assert set(fused) == {1, 2}
    assert fused[1] > fused[2]


def test_rrf_handles_no_rankings() -> None:
    assert reciprocal_rank_fusion({}, k=60) == {}


def test_rrf_rejects_non_positive_k() -> None:
    with pytest.raises(ValueError):
        reciprocal_rank_fusion({"fuzzy": [1]}, k=0)


def test_small_k_makes_the_top_rank_dominate() -> None:
    """k controls how much first place is worth; I picked 60 to flatten it"""
    flat = reciprocal_rank_fusion({"a": [1, 2]}, k=60)
    sharp = reciprocal_rank_fusion({"a": [1, 2]}, k=1)

    assert flat[1] / flat[2] < sharp[1] / sharp[2]


def test_max_rrf_score_matches_a_clean_sweep() -> None:
    rankings = {"fuzzy": [1, 2], "amount": [1, 2], "embedding": [1, 2]}
    fused = reciprocal_rank_fusion(rankings, k=60)

    assert fused[1] == pytest.approx(max_rrf_score(len(rankings), k=60))


def test_normalized_confidence_stays_within_zero_and_one() -> None:
    rankings = {"fuzzy": [5, 6, 7], "amount": [6, 5, 7]}
    fused = reciprocal_rank_fusion(rankings, k=60)
    best = max_rrf_score(len(rankings), k=60)

    for score in fused.values():
        assert 0.0 <= score / best <= 1.0


def test_cosine_similarity_basics() -> None:
    assert cosine_similarity([1.0, 0.0], [1.0, 0.0]) == pytest.approx(1.0)
    assert cosine_similarity([1.0, 0.0], [0.0, 1.0]) == pytest.approx(0.0)
    # I return 0.0 rather than raising when a vector is missing or mismatched
    assert cosine_similarity([], [1.0]) == 0.0
    assert cosine_similarity([1.0, 2.0], [1.0]) == 0.0
    assert cosine_similarity([0.0, 0.0], [1.0, 1.0]) == 0.0


def test_amount_similarity_ignores_sign() -> None:
    """A statement may show a payment negative while the expense is positive"""
    assert amount_similarity(Decimal("100"), Decimal("-100")) == pytest.approx(1.0)
    assert amount_similarity(Decimal("100"), Decimal("95")) == pytest.approx(0.95)
    assert amount_similarity(Decimal("0"), Decimal("0")) == pytest.approx(1.0)


def test_date_similarity_decays_across_the_window() -> None:
    same_day = date(2026, 9, 14)
    assert date_similarity(same_day, same_day, window_days=5) == pytest.approx(1.0)
    assert date_similarity(same_day, date(2026, 9, 19), window_days=5) == pytest.approx(
        0.0
    )
    assert date_similarity(same_day, date(2026, 9, 16), window_days=5) == pytest.approx(
        0.6
    )
