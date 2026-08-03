"""Domain exceptions mapped to HTTP status codes by the API layer"""


class ReckonFlowError(Exception):
    """Base error for expected business failures"""


class UnbalancedLedgerError(ReckonFlowError):
    """Transaction debits and credits do not cancel out"""


class NotFoundError(ReckonFlowError):
    """Requested domain entity does not exist"""


class InvalidStateTransitionError(ReckonFlowError):
    """Illegal approval or expense status change"""


class ConflictError(ReckonFlowError):
    """Concurrency or uniqueness conflict"""
