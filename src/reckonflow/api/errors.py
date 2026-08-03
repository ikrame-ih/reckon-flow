"""I translate domain exceptions into HTTP responses

The service layer raises meaning ("this transition is illegal"), not status
codes. Mapping them once here keeps HTTP out of the domain and guarantees
every error leaves the API in the same JSON shape
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

# I keep the mapping as data so the table of "which error means what over
# HTTP" is readable in one glance
ERROR_STATUS_MAP: dict[type[ReckonFlowError], int] = {
    NotFoundError: status.HTTP_404_NOT_FOUND,
    # 409 rather than 400: the request is well-formed, it just lost a race or
    # asked for a move the current state does not allow
    ConflictError: status.HTTP_409_CONFLICT,
    InvalidStateTransitionError: status.HTTP_409_CONFLICT,
    # I write 422 as a literal because Starlette renamed the constant and I do
    # not want the app to depend on which spelling the installed version has
    UnbalancedLedgerError: 422,
}


def _error_response(exc: ReckonFlowError, status_code: int) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"error": type(exc).__name__, "detail": str(exc)},
    )


def register_exception_handlers(app: FastAPI) -> None:
    """I attach one handler per domain error, plus a catch-all base handler"""

    async def handle_known(request: Request, exc: Exception) -> JSONResponse:
        assert isinstance(exc, ReckonFlowError)
        return _error_response(exc, ERROR_STATUS_MAP[type(exc)])

    for error_type in ERROR_STATUS_MAP:
        app.add_exception_handler(error_type, handle_known)

    async def handle_base(request: Request, exc: Exception) -> JSONResponse:
        """I catch domain errors I have not mapped yet

        A new subclass should surface as a clean 400, not a 500 that looks
        like a crash in the logs
        """
        assert isinstance(exc, ReckonFlowError)
        logger.warning(
            "api.unmapped_domain_error",
            error=type(exc).__name__,
            detail=str(exc),
            path=request.url.path,
        )
        return _error_response(exc, status.HTTP_400_BAD_REQUEST)

    app.add_exception_handler(ReckonFlowError, handle_base)
