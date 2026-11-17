"""Error responses in the API_CONTRACT.md shape:

    {"error": {"code", "message", "field_errors", "retryable"}, "request_id": "..."}

`detail` is also returned, unchanged from FastAPI's default, as a deprecated alias so
existing clients keep working during the transition. Never put stack traces, paths,
provider responses or signed URLs in a public error.
"""

from __future__ import annotations

import logging
import re
import uuid
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger(__name__)

_CODES = {
    400: "BAD_REQUEST",
    401: "UNAUTHORIZED",
    403: "FORBIDDEN",
    404: "NOT_FOUND",
    405: "METHOD_NOT_ALLOWED",
    409: "CONFLICT",
    413: "PAYLOAD_TOO_LARGE",
    422: "VALIDATION_ERROR",
    429: "RATE_LIMITED",
    500: "INTERNAL_ERROR",
    503: "SERVICE_UNAVAILABLE",
}
_RETRYABLE = {429, 500, 502, 503, 504}
_REQUEST_ID = re.compile(r"^[A-Za-z0-9._\-]{1,64}$")


def request_id_for(request: Request) -> str:
    """Reuse a well-formed client X-Request-Id, otherwise generate one."""
    existing = getattr(request.state, "request_id", None)
    if existing:
        return existing
    supplied = request.headers.get("X-Request-Id", "")
    rid = supplied if _REQUEST_ID.match(supplied) else str(uuid.uuid4())
    request.state.request_id = rid
    return rid


def _body(
    request: Request,
    status: int,
    message: str,
    *,
    detail: Any,
    field_errors: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    return {
        "error": {
            "code": _CODES.get(status, "ERROR"),
            "message": message,
            "field_errors": field_errors or [],
            "retryable": status in _RETRYABLE,
        },
        "request_id": request_id_for(request),
        "detail": detail,  # deprecated alias, see module docstring
    }


def _respond(
    request: Request, status: int, body: dict, headers: dict | None = None
) -> JSONResponse:
    out = dict(headers or {})
    out["X-Request-Id"] = body["request_id"]
    return JSONResponse(status_code=status, content=body, headers=out)


async def http_error(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    detail = exc.detail
    field_errors: list[dict[str, str]] = []
    if isinstance(detail, dict):
        message = str(detail.get("message", "Request failed"))
        field_errors = [{"field": "", "message": str(e)} for e in detail.get("errors", [])]
    else:
        message = str(detail)
    body = _body(request, exc.status_code, message, detail=detail, field_errors=field_errors)
    return _respond(request, exc.status_code, body, getattr(exc, "headers", None))


async def validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
    errors = exc.errors()
    field_errors = [
        {
            "field": ".".join(str(p) for p in e.get("loc", ()) if p != "body"),
            "message": str(e.get("msg", "invalid")),
        }
        for e in errors
    ]
    # `detail` mirrors FastAPI's default list (minus raw input values, which may be personal data).
    detail = [{k: v for k, v in e.items() if k in ("loc", "msg", "type")} for e in errors]
    body = _body(request, 422, "Some fields are invalid.", detail=detail, field_errors=field_errors)
    return _respond(request, 422, body)


async def unhandled_error(request: Request, exc: Exception) -> JSONResponse:
    rid = request_id_for(request)
    logger.exception("unhandled error (request_id=%s)", rid)
    body = _body(
        request, 500, "Something went wrong. Please try again.", detail="Internal Server Error"
    )
    return _respond(request, 500, body)


def install(app: FastAPI) -> None:
    app.add_exception_handler(StarletteHTTPException, http_error)  # type: ignore[arg-type]
    app.add_exception_handler(HTTPException, http_error)  # type: ignore[arg-type]
    app.add_exception_handler(RequestValidationError, validation_error)  # type: ignore[arg-type]
    app.add_exception_handler(Exception, unhandled_error)
