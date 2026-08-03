"""Map domain exceptions to HTTP responses

Services raise meaning ("this transition is illegal"), not status codes.
Central mapping keeps HTTP out of the domain and uniform error JSON.
"""

from __future__ import annotations

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse

from reckonflow.core.exceptions import (
    ConflictError,
    InvalidStateTransitionError,
    NotFoundError,
    ReckonFlowError,
    UnbalancedLedgerError,
)
from reckonflow.core.logging import get_logger

logger = get_logger(__name__)

# Readable table of which domain error maps to which HTTP status
ERROR_STATUS_MAP: dict[type[ReckonFlowError], int] = {
    NotFoundError: status.HTTP_404_NOT_FOUND,
    # 409 rather than 400: the request is well-formed, it just lost a race or
    # asked for a move the current state does not allow
    ConflictError: status.HTTP_409_CONFLICT,
    InvalidStateTransitionError: status.HTTP_409_CONFLICT,
    # 422 literal — Starlette renamed the constant across versions
    UnbalancedLedgerError: 422,
}


def _error_response(exc: ReckonFlowError, status_code: int) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"error": type(exc).__name__, "detail": str(exc)},
    )


def register_exception_handlers(app: FastAPI) -> None:
    """Attach one handler per domain error plus a catch-all base handler"""

    async def handle_known(request: Request, exc: Exception) -> JSONResponse:
        assert isinstance(exc, ReckonFlowError)
        return _error_response(exc, ERROR_STATUS_MAP[type(exc)])

    for error_type in ERROR_STATUS_MAP:
        app.add_exception_handler(error_type, handle_known)

    async def handle_base(request: Request, exc: Exception) -> JSONResponse:
        """Unmapped domain errors become 400, not opaque 500s"""
        assert isinstance(exc, ReckonFlowError)
        logger.warning(
            "api.unmapped_domain_error",
            error=type(exc).__name__,
            detail=str(exc),
            path=request.url.path,
        )
        return _error_response(exc, status.HTTP_400_BAD_REQUEST)

    app.add_exception_handler(ReckonFlowError, handle_base)
