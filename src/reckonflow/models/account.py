"""I define a plain Account shape for learning (no database yet)

Later I will turn this idea into a SQLAlchemy model
"""

from dataclasses import dataclass


@dataclass
class Account:
    """I represent one ledger account (a named money bucket)"""

    code: str
    name: str
    currency: str = "EUR"

    def label(self) -> str:
        """I return a short human-readable label"""
        return f"{self.code} — {self.name} ({self.currency})"
