"""One error envelope for the whole API.

Every non-2xx response, from any view, looks like this:

    {"ok": false, "error": {"code": "validation_error", "message": "...", "details": {...}}}

Two rules that the previous application broke and that this handler enforces:

  * An error is never returned with HTTP 200. The status code carries meaning.
  * A stack trace or a raw database message never reaches a browser. The user
    gets a request id; the log gets the exception.
"""

from __future__ import annotations

import logging

from django.core.exceptions import PermissionDenied as DjangoPermissionDenied
from django.db import DatabaseError, IntegrityError
from django.http import Http404
from rest_framework import status as drf_status
from rest_framework.response import Response
from rest_framework.views import exception_handler as drf_exception_handler

from core.exceptions import HTTP_STATUS_CODES, DomainError
from core.middleware import get_request_id

logger = logging.getLogger("opstracking.errors")


def handle(exc, context):
    request = context.get("request")
    path = getattr(request, "path", "?")

    # ── expected business-rule failures ──────────────────────
    if isinstance(exc, DomainError):
        if exc.http_status >= 500:
            logger.error("domain error %s at %s: %s", exc.code, path, exc.message)
        return _envelope(exc.code, exc.message, exc.http_status, exc.details)

    if isinstance(exc, Http404):
        return _envelope("not_found", "Not found.", 404)

    if isinstance(exc, DjangoPermissionDenied):
        return _envelope("forbidden", "You do not have permission to do that.", 403)

    # ── anything DRF already understands ─────────────────────
    response = drf_exception_handler(exc, context)
    if response is not None:
        code = HTTP_STATUS_CODES.get(response.status_code, "error")
        message, details = _flatten(response.data)
        response.data = {"ok": False, "error": {"code": code, "message": message,
                                                "details": details}}
        return response

    # ── integrity errors: a real conflict, not a crash ───────
    if isinstance(exc, IntegrityError):
        logger.warning("integrity error at %s: %s", path, exc)
        return _envelope(
            "conflict",
            "That change conflicts with an existing record.",
            409,
        )

    # ── everything else is a bug ─────────────────────────────
    request_id = get_request_id()
    if isinstance(exc, DatabaseError):
        logger.exception("database error at %s", path, extra={"request_id": request_id})
    else:
        logger.exception("unhandled exception at %s", path, extra={"request_id": request_id})

    return _envelope(
        "server_error",
        f"Something went wrong on our side. Reference: {request_id}",
        drf_status.HTTP_500_INTERNAL_SERVER_ERROR,
    )


def _envelope(code: str, message: str, http_status: int, details: dict | None = None) -> Response:
    return Response(
        {"ok": False, "error": {"code": code, "message": message, "details": details or {}}},
        status=http_status,
    )


def _flatten(data) -> tuple[str, dict]:
    """Turn DRF's nested validation structure into one readable sentence plus
    the full structure for a form to highlight fields with.

    {"email": ["This field is required."]} → ("Email: This field is required.", {...})
    """
    if isinstance(data, dict):
        detail = data.get("detail")
        if detail is not None and len(data) == 1:
            return str(detail), {}

        parts = []
        for field, errors in data.items():
            label = field.replace("_", " ").capitalize()
            if isinstance(errors, (list, tuple)):
                parts.append(f"{label}: {' '.join(str(e) for e in errors)}")
            elif isinstance(errors, dict):
                nested, _ = _flatten(errors)
                parts.append(f"{label}: {nested}")
            else:
                parts.append(f"{label}: {errors}")
        return " ".join(parts), dict(data)

    if isinstance(data, (list, tuple)):
        return " ".join(str(e) for e in data), {}

    return str(data), {}
