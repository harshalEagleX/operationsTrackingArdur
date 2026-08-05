#!/usr/bin/env python
"""Django's command-line utility for administrative tasks."""
import os
import sys
from pathlib import Path

import environ

BASE_DIR = Path(__file__).resolve().parent

# Read .env before Django touches settings, so DJANGO_SETTINGS_MODULE can live
# there rather than being exported by hand in every shell.
env_file = BASE_DIR / ".env"
if env_file.exists():
    environ.Env.read_env(str(env_file))


def main() -> None:
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "opstracking.settings.dev")
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:  # pragma: no cover
        raise ImportError(
            "Couldn't import Django. Is it installed and is your virtualenv "
            "activated? Try: source .venv/bin/activate && pip install -r requirements-dev.txt"
        ) from exc
    execute_from_command_line(sys.argv)


if __name__ == "__main__":
    main()
