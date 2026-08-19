"""Smoke checks for the synthetic matching dataset — no invented metrics."""

from __future__ import annotations

import json
import runpy
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATASET = ROOT / "evals" / "dataset" / "cases.json"


def test_matching_dataset_size_and_gold() -> None:
    payload = json.loads(DATASET.read_text(encoding="utf-8"))
    cases = payload["cases"]
    assert 30 <= len(cases) <= 50
    assert payload["n"] == len(cases)
    for case in cases:
        ids = [row["id"] for row in case["candidates"]]
        assert len(ids) == len(set(ids))
        assert case["gold_id"] in ids


def test_matching_eval_rates_are_probabilities() -> None:
    mod = runpy.run_path(str(ROOT / "scripts" / "run_matching_evals.py"))
    report = mod["evaluate"]()
    assert set(report) == {"fuzzy", "embeddings", "hybrid"}
    for row in report.values():
        assert 0.0 <= row["hit_at_1"] <= 1.0
        assert 0.0 <= row["hit_at_3"] <= 1.0
        assert row["hit_at_1"] <= row["hit_at_3"] + 1e-9
        assert row["hit_at_1_count"] <= row["n"]
