"""I define domain exceptions the API layer can map to HTTP status codes"""


class ReckonFlowError(Exception):
    """I am the base error for expected business failures"""


class UnbalancedLedgerError(ReckonFlowError):
    """I signal a transaction whose debits and credits do not cancel out"""


class NotFoundError(ReckonFlowError):
    """I signal a missing domain entity"""


class InvalidStateTransitionError(ReckonFlowError):
    """I signal an illegal approval or expense status change"""


class ConflictError(ReckonFlowError):
    """I signal a concurrency or uniqueness conflict"""
