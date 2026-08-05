"""Rate limits.

Rates live in settings.REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"] so they are
tunable without a code change. Views opt in with ``throttle_scope``.
"""

from __future__ import annotations

from rest_framework.throttling import ScopedRateThrottle, SimpleRateThrottle


class EmployeeScopedThrottle(ScopedRateThrottle):
    """Scoped throttle keyed on emp_id rather than IP.

    An ops floor sits behind one office NAT, so IP-based throttling would
    punish the whole team for one person's fast clicking.
    """

    def get_cache_key(self, request, view):
        scope = getattr(view, self.scope_attr, None)
        if not scope:
            return None

        user = getattr(request, "user", None)
        if user and user.is_authenticated:
            ident = getattr(user, "emp_id", None) or user.pk
        else:
            ident = self.get_ident(request)

        return self.cache_format % {"scope": scope, "ident": ident}


class LoginThrottle(SimpleRateThrottle):
    """Brute-force guard on the login endpoint.

    Keyed on the submitted emp_id *and* the client IP, so one attacker cannot
    lock a real employee out by hammering their username from elsewhere.
    """

    scope = "login"

    def get_cache_key(self, request, view):
        emp_id = ""
        if request.method == "POST":
            emp_id = str(request.data.get("emp_id", ""))[:20]
        return self.cache_format % {
            "scope": self.scope,
            "ident": f"{self.get_ident(request)}:{emp_id}",
        }


class UploadThrottle(EmployeeScopedThrottle):
    scope = "upload"


class ChatBurstThrottle(EmployeeScopedThrottle):
    """Reserved for apps.chat when it is built."""

    scope = "chat_send"


class ReportExportThrottle(EmployeeScopedThrottle):
    """Excel generation is expensive even on a background worker."""

    scope = "report_export"
