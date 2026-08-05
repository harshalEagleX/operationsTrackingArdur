"""Jinja2 environment for the application's own screens.

The templates ported from Flask are Jinja2, so they keep working with only the
url_for → url swap. autoescape is on and stays on.
"""

from django.conf import settings
from django.templatetags.static import static
from django.urls import reverse
from django.utils.html import escape
from jinja2 import Environment
from markupsafe import Markup

from core.timezone import now_ist, today_ist


def csrf_input(request) -> Markup:
    """Render the hidden CSRF field. Jinja2 has no {% csrf_token %} tag."""
    from django.middleware.csrf import get_token

    token = get_token(request)
    return Markup(f'<input type="hidden" name="csrfmiddlewaretoken" value="{escape(token)}">')


def csrf_token(request) -> str:
    from django.middleware.csrf import get_token

    return get_token(request)


def environment(**options) -> Environment:
    options.setdefault("autoescape", True)
    env = Environment(**options)
    env.globals.update(
        {
            "static": static,
            "url": reverse,
            "csrf_input": csrf_input,
            "csrf_token": csrf_token,
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
