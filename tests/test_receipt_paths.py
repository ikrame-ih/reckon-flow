"""Receipt path sanitization and storage directory containment"""

from __future__ import annotations

from pathlib import Path

import pytest

from reckonflow.core.exceptions import NotFoundError
from reckonflow.services.receipts import ReceiptService, safe_filename


def test_safe_filename_strips_path_segments() -> None:
    assert ".." not in safe_filename("../../etc/passwd")
    assert "/" not in safe_filename("a/b/c.pdf")
    assert safe_filename("invoice.pdf") == "invoice.pdf"


def test_resolve_storage_path_rejects_escape(tmp_path: Path) -> None:
    service = ReceiptService.__new__(ReceiptService)
    service._storage = tmp_path
    outside = tmp_path.parent / "outside.txt"
    outside.write_text("x", encoding="utf-8")
    with pytest.raises(NotFoundError):
        service._resolve_storage_path(outside)
