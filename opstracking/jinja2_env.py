"""Jinja2 environment for the application's own screens.

The templates ported from Flask are Jinja2, so they keep working with only the
url_for → url swap. autoescape is on and stays on.
"""

from django.conf import settings
from django.templatetags.static import static
from django.urls import reverse
from jinja2 import Environment

from core.timezone import now_ist, today_ist


def environment(**options) -> Environment:
    options.setdefault("autoescape", True)
    env = Environment(**options)
    # Note: `csrf_input` and `csrf_token` are NOT defined here. Django's
    # Jinja2 backend already injects both into every context as lazy
    # *values*, so templates write `{{ csrf_input }}` — not a function call.
    env.globals.update(
        {
            "static": static,
            "url": reverse,
            "now_ist": now_ist,
            "today_ist": today_ist,
            "DEBUG": settings.DEBUG,
            "FEATURES": {
                "chat": settings.FEATURE_CHAT,
                "presence": settings.FEATURE_PRESENCE,
                "notifications": settings.FEATURE_NOTIFICATIONS,
            },
        }
    )
    env.filters.update(
        {
            "ist": lambda dt, fmt="%d %b %Y, %I:%M %p": dt.strftime(fmt) if dt else "",
            "duration": _format_duration,
        }
    )
    return env


def _format_duration(seconds) -> str:
    """3725 → '1h 02m'. None and 0 render as an em dash, not '0h 00m'."""
    if not seconds:
        return "—"
    seconds = int(seconds)
    hours, remainder = divmod(seconds, 3600)
    minutes = remainder // 60
    if hours:
        return f"{hours}h {minutes:02d}m"
    return f"{minutes}m"
