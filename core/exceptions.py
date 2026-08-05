"""Domain exception hierarchy.

Services raise these. The DRF exception handler (core/exception_handler.py)
turns them into the one JSON error envelope the frontend understands.

Services must never raise DRF exceptions directly — that would couple the
business layer to the transport layer, and the same service has to work when
called from a Celery task or a management command where there is no request.
"""

from __future__ import annotations


class DomainError(Exception):
    """Base class for every expected business-rule failure.

    Unexpected failures are not DomainErrors — they are bugs, and the handler
    logs them with a stack trace and returns a generic 500.
    """

    http_status = 400
    code = "domain_error"

    def __init__(self, message: str, *, code: str | None = None, details: dict | None = None):
        super().__init__(message)
        self.message = message
        if code:
            self.code = code
        self.details = details or {}


class ValidationError(DomainError):
    http_status = 400
    code = "validation_error"


class NotFoundError(DomainError):
    http_status = 404
    code = "not_found"


class PermissionDeniedError(DomainError):
    http_status = 403
    code = "forbidden"


class AuthenticationError(DomainError):
    http_status = 401
    code = "unauthenticated"


class ConflictError(DomainError):
    """The request is valid but collides with current state — a second break
    started while one is already running, a duplicate master record."""

    http_status = 409
    code = "conflict"


class RateLimitError(DomainError):
    http_status = 429
    code = "rate_limited"


class NotImplementedYetError(DomainError):
    """A route that exists so the frontend has something to call, but whose
    implementation is deliberately deferred. Returns 501, and the handler
    logs it so deferred work stays visible instead of silently rotting."""

    http_status = 501
    code = "not_implemented"


# Convenience map used by the exception handler for non-domain DRF errors.
HTTP_STATUS_CODES = {
    400: "validation_error",
    401: "unauthenticated",
    403: "forbidden",
    404: "not_found",
    405: "method_not_allowed",
    409: "conflict",
    413: "payload_too_large",
    415: "unsupported_media_type",
    429: "rate_limited",
    500: "server_error",
    501: "not_implemented",
    502: "upstream_error",
    503: "unavailable",
}
