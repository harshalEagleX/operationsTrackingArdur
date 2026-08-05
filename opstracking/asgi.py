"""ASGI entry point — served by Daphne on 127.0.0.1:8002.

Import order matters: get_asgi_application() must run before anything that
touches models, or Django's app registry is not ready yet.
"""

import os
from pathlib import Path

import environ

BASE_DIR = Path(__file__).resolve().parent.parent
env_file = BASE_DIR / ".env"
if env_file.exists():
    environ.Env.read_env(str(env_file))

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "opstracking.settings.prod")

from django.core.asgi import get_asgi_application  # noqa: E402

django_asgi_app = get_asgi_application()

from channels.routing import ProtocolTypeRouter, URLRouter  # noqa: E402
from channels.security.websocket import AllowedHostsOriginValidator  # noqa: E402
from channels.sessions import SessionMiddlewareStack  # noqa: E402

from apps.realtime.middleware import TicketAuthMiddleware  # noqa: E402
from opstracking.routing import websocket_urlpatterns  # noqa: E402

application = ProtocolTypeRouter(
    {
        # Daphne can serve HTTP too, but Apache routes it to Gunicorn instead.
        # This entry exists so /health/ works when probing :8002 directly.
        "http": django_asgi_app,
        "websocket": AllowedHostsOriginValidator(
            TicketAuthMiddleware(
                SessionMiddlewareStack(
                    URLRouter(websocket_urlpatterns),
                )
            )
        ),
    }
)
