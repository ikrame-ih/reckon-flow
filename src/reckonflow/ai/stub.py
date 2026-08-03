"""I extract receipt fields with plain rules, no model and no network

I exist for three reasons: CI must pass without an API key, the demo must work
offline, and the eval suite needs a baseline to beat. If the LLM cannot score
better than these regexes on the fixtures, it is not earning its latency
"""

from __future__ import annotations

import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from reckonflow.ai.base import ExtractionError
from reckonflow.schemas.receipt import ReceiptExtraction, ReceiptLineItem

_CURRENCY_SYMBOLS = {"€": "EUR", "$": "USD", "£": "GBP"}
_CURRENCY_CODES = ("EUR", "USD", "GBP", "CHF", "MAD", "SEK")

_DATE_PATTERNS: tuple[tuple[str, str], ...] = (
    (r"\b(\d{4}-\d{2}-\d{2})\b", "%Y-%m-%d"),
    (r"\b(\d{2}/\d{2}/\d{4})\b", "%d/%m/%Y"),
    (r"\b(\d{2}\.\d{2}\.\d{4})\b", "%d.%m.%Y"),
)

# I match the last money-looking token on a line, which is where receipts
# always put the amount
_AMOUNT_RE = re.compile(
    r"(-?\d{1,3}(?:[ .,]\d{3})*(?:[.,]\d{1,2})?|-?\d+(?:[.,]\d{1,2})?)"
)

_TOTAL_WORDS = ("total", "amount due", "grand total", "zu zahlen", "montant")
_SUBTOTAL_WORDS = ("subtotal", "sub-total", "net", "netto", "sous-total")
_VAT_WORDS = ("vat", "tax", "mwst", "tva", "btw", "iva")
_NOISE_WORDS = (
    "thank you",
    "invoice",
    "receipt",
    "customer",
    "card",
    "terminal",
    "change",
    "cash",
    "payment",
    "tel",
    "vat id",
    "reg no",
)


def _normalize_amount(token: str) -> str:
    """I turn 1.234,56 / 1,234.56 / 1 234.56 into a plain decimal string"""
    text = token.strip().replace(" ", "").replace("\u00a0", "")
    if "," in text and "." in text:
        # Whichever separator comes last is the decimal one
        if text.rfind(",") > text.rfind("."):
            text = text.replace(".", "").replace(",", ".")
        else:
            text = text.replace(",", "")
    elif "," in text:
        # A comma with one or two digits behind it is a decimal separator;
        # anything longer is a thousands group such as 1,234
        tail = text.split(",")[-1]
        text = text.replace(",", ".") if len(tail) <= 2 else text.replace(",", "")
    return text


def _amount_on_line(line: str) -> str | None:
    """I return the last parseable amount on a line, or None"""
    for token in reversed(_AMOUNT_RE.findall(line)):
        candidate = _normalize_amount(token)
        try:
            Decimal(candidate)
        except InvalidOperation:
            continue
        if any(ch.isdigit() for ch in candidate):
            return candidate
    return None


def _find_date(text: str) -> date | None:
    for pattern, fmt in _DATE_PATTERNS:
        match = re.search(pattern, text)
        if match:
            try:
                return datetime.strptime(match.group(1), fmt).date()
            except ValueError:
                continue
    return None


def _find_currency(text: str) -> str:
    for symbol, code in _CURRENCY_SYMBOLS.items():
        if symbol in text:
            return code
    upper = text.upper()
    for code in _CURRENCY_CODES:
        if re.search(rf"\b{code}\b", upper):
            return code
    return "EUR"


def _looks_like_line_item(line: str) -> bool:
    lowered = line.lower()
    if any(word in lowered for word in _TOTAL_WORDS + _SUBTOTAL_WORDS + _VAT_WORDS):
        return False
    if any(word in lowered for word in _NOISE_WORDS):
        return False
    # A line item needs a description and an amount, not just an amount
    stripped = _AMOUNT_RE.sub("", line).strip(" .:-\t|")
    return len(stripped) >= 3 and _amount_on_line(line) is not None


class StubReceiptExtractor:
    """I read receipt text with regexes so nothing depends on a provider"""

    name = "stub"

    async def extract(self, *, raw_text: str, filename: str) -> ReceiptExtraction:
        """I pull vendor, date, totals, VAT, and line items out of plain text"""
        lines = [line.strip() for line in raw_text.splitlines() if line.strip()]
        if not lines:
            raise ExtractionError(f"{filename} contains no readable text")

        vendor = self._find_vendor(lines)
        total = self._find_labelled(lines, _TOTAL_WORDS, exclude=_SUBTOTAL_WORDS)
        subtotal = self._find_labelled(lines, _SUBTOTAL_WORDS)
        vat_amount = self._find_labelled(lines, _VAT_WORDS)
        vat_rate = self._find_vat_rate(lines)

        if total is None:
            # Without a total I cannot reconcile anything, so I refuse rather
            # than return a plausible-looking but useless record
            raise ExtractionError(f"I found no total on {filename}")

        return ReceiptExtraction(
            vendor=vendor,
            receipt_date=_find_date(raw_text),
            currency=_find_currency(raw_text),
            subtotal=subtotal,
            vat_amount=vat_amount,
            vat_rate=vat_rate,
            total=total,
            line_items=self._find_line_items(lines),
        )

    def _find_vendor(self, lines: list[str]) -> str:
        for line in lines:
            if ":" in line and line.split(":", 1)[0].strip().lower() in {
                "vendor",
                "merchant",
                "supplier",
            }:
                return line.split(":", 1)[1].strip()[:160]
        # Receipts print the merchant name first; I fall back to that
        for line in lines:
            if not _AMOUNT_RE.fullmatch(line.strip()):
                return line.strip(" *#-")[:160]
        return lines[0][:160]

    def _find_labelled(
        self,
        lines: list[str],
        words: tuple[str, ...],
        *,
        exclude: tuple[str, ...] = (),
    ) -> str | None:
        """I scan from the bottom because summary lines sit at the end"""
        for line in reversed(lines):
            lowered = line.lower()
            if any(bad in lowered for bad in exclude):
                continue
            if any(word in lowered for word in words):
                amount = _amount_on_line(line)
                if amount is not None:
                    return amount
        return None

    def _find_vat_rate(self, lines: list[str]) -> str | None:
        for line in lines:
            lowered = line.lower()
            if any(word in lowered for word in _VAT_WORDS):
                match = re.search(r"(\d{1,2}(?:[.,]\d)?)\s*%", line)
                if match:
                    return _normalize_amount(match.group(1))
        return None

    def _find_line_items(self, lines: list[str]) -> list[ReceiptLineItem]:
        items: list[ReceiptLineItem] = []
        for line in lines[1:]:
            if not _looks_like_line_item(line):
                continue
            amount = _amount_on_line(line)
            if amount is None:
                continue
            description = _AMOUNT_RE.sub("", line).strip(" .:-\t|x×*")
            if not description:
                continue
            quantity = "1"
            qty_match = re.match(r"^(\d{1,3})\s*[x×]\s*(.+)$", description, re.I)
            if qty_match:
                quantity = qty_match.group(1)
                description = qty_match.group(2).strip()
            items.append(
                ReceiptLineItem(
                    description=description[:300], quantity=quantity, total=amount
                )
            )
        return items
