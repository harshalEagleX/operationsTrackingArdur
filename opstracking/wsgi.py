"""WSGI entry point — served by Gunicorn on 127.0.0.1:8001.

Handles DRF/JSON and the Jinja2 pages. WebSockets go to asgi.py instead; see
the architecture doc §1.1 for why these are two processes and not one.
"""

import os
from pathlib import Path

import environ
from django.core.wsgi import get_wsgi_application

BASE_DIR = Path(__file__).resolve().parent.parent
env_file = BASE_DIR / ".env"
if env_file.exists():
    environ.Env.read_env(str(env_file))

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "opstracking.settings.prod")

application = get_wsgi_application()
