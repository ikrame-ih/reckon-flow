"""Deterministic embedding helper"""

from reckonflow.core.embeddings import text_embedding


def test_text_embedding_is_normalised_and_deterministic() -> None:
    first = text_embedding("Hotel Adlon Berlin")
    second = text_embedding("Hotel Adlon Berlin")
    other = text_embedding("Lufthansa flight ticket")

    assert first == second
    assert len(first) == 384
    assert abs(sum(value * value for value in first) - 1.0) < 1e-6
    assert first != other
