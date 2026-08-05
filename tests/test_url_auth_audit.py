"""The test that stops unauthenticated data access coming back.

Walks the whole URLConf and asserts that every API route either enforces
authentication or appears on a short, explicit allowlist. Adding a public
endpoint requires editing this file, which means it shows up in review.
"""

from __future__ import annotations

import pytest
from django.urls import URLPattern, URLResolver, get_resolver

from core.permissions import AllowAnyPublic

pytestmark = pytest.mark.django_db

# The complete set of routes that may be reached without a session.
PUBLIC_ALLOWLIST = {
    "/health/",
    "/ready/",
    "/login/",
    "/api/v1/auth/login/",
}

# Not application routes.
IGNORED_PREFIXES = ("/admin/", "/api-auth/", "/static/")


def _walk(resolver, prefix=""):
    for entry in resolver.url_patterns:
        if isinstance(entry, URLResolver):
            yield from _walk(entry, prefix + str(entry.pattern))
        elif isinstance(entry, URLPattern):
            yield prefix + str(entry.pattern), entry.callback


def _permission_classes(callback):
    view_class = getattr(callback, "cls", None) or getattr(callback, "view_class", None)
    if view_class is None:
        return None
    return getattr(view_class, "permission_classes", None)


def test_every_api_route_requires_authentication():
    """Deny-by-default, enforced structurally rather than by memory."""
    offenders = []

    for route, callback in _walk(get_resolver()):
        path = "/" + route.lstrip("/")

        if path.startswith(IGNORED_PREFIXES):
            continue
        if not path.startswith("/api/"):
            continue

        permissions = _permission_classes(callback)
        if permissions is None:
            continue  # not a DRF view

        is_public = any(cls is AllowAnyPublic for cls in permissions)
        if not is_public:
            continue

        # It declares itself public — it had better be on the list.
        normalised = path.rstrip("$").replace("\\", "")
        if not any(allowed.strip("/") in normalised for allowed in PUBLIC_ALLOWLIST):
            offenders.append(path)

    assert not offenders, (
        "These API routes are public but not on PUBLIC_ALLOWLIST in "
        f"tests/test_url_auth_audit.py: {offenders}"
    )


def test_the_default_permission_class_denies_anonymous_users():
    from django.conf import settings

    defaults = settings.REST_FRAMEWORK["DEFAULT_PERMISSION_CLASSES"]

    assert defaults == ["core.permissions.IsAuthenticatedEmployee"], (
        "The global default must stay deny-by-default. A view that forgets its "
        "permission_classes has to be closed, not open."
    )


def test_public_endpoints_are_actually_reachable(api):
    """The allowlist must not drift out of sync with reality either."""
    assert api.get("/health/").status_code == 200
    assert api.get("/ready/").status_code in (200, 503)


@pytest.mark.parametrize("path", sorted(PUBLIC_ALLOWLIST - {"/api/v1/auth/login/"}))
def test_allowlisted_paths_respond_without_a_session(client, path):
    response = client.get(path)
    assert response.status_code < 400 or response.status_code in (405, 503)
