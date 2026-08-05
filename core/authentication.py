"""Authentication classes.

The application is session-authenticated: same origin, HttpOnly cookie, CSRF
enforced on unsafe methods. There is no token API surface, because there is no
third-party consumer — adding JWTs would be a second auth path to secure for
no caller.
"""

from __future__ import annotations

from rest_framework.authentication import SessionAuthentication


class CsrfExemptSessionAuthentication(SessionAuthentication):
    """Session auth without the CSRF check.

    Only for endpoints that cannot carry a CSRF token and are safe without one
    — currently none. Kept documented rather than deleted so that anyone
    reaching for it has to justify it in review.
    """

    def enforce_csrf(self, request):  # pragma: no cover
        return


def get_user_from_session_key(session_key: str):
    """Resolve a Django session key to a user.

    Used by the WebSocket ticket flow, which authenticates once at handshake
    and therefore needs the user without a request object.
    """
    from django.contrib.auth import get_user_model
    from django.contrib.sessions.backends.db import SessionStore

    if not session_key:
        return None

    session = SessionStore(session_key=session_key)
    user_id = session.get("_auth_user_id")
    if not user_id:
        return None

    return get_user_model().objects.filter(pk=user_id).first()
