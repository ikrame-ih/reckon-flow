"""Score receipt extraction against annotated fixtures

Run: uv run python scripts/run_evals.py
Uses stub extractor when GROQ_API_KEY is empty so CI stays offline.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

from reckonflow.ai import get_receipt_extractor

FIXTURES = Path(__file__).resolve().parents[1] / "evals" / "receipts"

# Scored fields — missing optional expected fields do not fail the case
SCORED_FIELDS = (
    "vendor",
    "receipt_date",
    "currency",
    "total",
    "subtotal",
    "vat_amount",
    "vat_rate",
)


def _normalize(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip().lower()


async def evaluate() -> int:
    extractor = get_receipt_extractor()
    files = sorted(FIXTURES.glob("*.json"))
    if not files:
        print(f"No fixtures in {FIXTURES}")
        return 1

    hits = 0
    total = 0
    print(f"Extractor: {getattr(extractor, 'name', type(extractor).__name__)}")

    for path in files:
        payload = json.loads(path.read_text(encoding="utf-8"))
        expected: dict[str, Any] = payload["expected"]
        result = await extractor.extract(
            raw_text=payload["raw_text"], filename=path.name
        )
        got = result.model_dump(mode="json")
        case_hits = 0
        case_total = 0
        for field in SCORED_FIELDS:
            if field not in expected:
                continue
            case_total += 1
            total += 1
            if _normalize(got.get(field)) == _normalize(expected[field]):
                case_hits += 1
                hits += 1
        print(f"{path.stem}: {case_hits}/{case_total} fields")

    accuracy = (hits / total) if total else 0.0
    print(f"Overall field accuracy: {hits}/{total} = {accuracy:.1%}")
    return 0 if accuracy >= 0.5 else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(evaluate()))
