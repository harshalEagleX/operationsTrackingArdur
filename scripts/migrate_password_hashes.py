#!/usr/bin/env python
"""One-time migration of legacy bcrypt password hashes.

The Flask application stored bare bcrypt strings (``$2b$12$...``). Django
expects an algorithm prefix (``bcrypt$$2b$12$...``). This script adds it.

Idempotent: the WHERE clause only matches un-prefixed rows, so re-running is
harmless.

After this runs, everyone can sign in with their existing password, and Django
transparently upgrades each hash to BCryptSHA256 on their next successful
login. Within a few weeks the whole table is on the stronger scheme with zero
password resets.

    python scripts/migrate_password_hashes.py            # dry run
    python scripts/migrate_password_hashes.py --apply    # do it
"""

import argparse
import os
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

import django  # noqa: E402
import environ  # noqa: E402

env_file = BASE_DIR / ".env"
if env_file.exists():
    environ.Env.read_env(str(env_file))

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "opstracking.settings.prod")
django.setup()

from django.db import connection, transaction  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true",
                        help="Actually write. Without this it only reports.")
    args = parser.parse_args()

    with connection.cursor() as cursor:
        cursor.execute("SELECT COUNT(*) FROM ot_users WHERE password LIKE '$2%%'")
        pending = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM ot_users WHERE password LIKE 'bcrypt$%%'")
        already = cursor.fetchone()[0]

    print(f"{pending} hash(es) need prefixing")
    print(f"{already} already migrated")

    if pending == 0:
        print("Nothing to do.")
        return 0

    if not args.apply:
        print("\nDry run. Re-run with --apply to write the change.")
        return 0

    print("\nTake a database backup before continuing.")
    if input("Type 'yes' to proceed: ").strip().lower() != "yes":
        print("Aborted.")
        return 1

    with transaction.atomic(), connection.cursor() as cursor:
        cursor.execute(
            "UPDATE ot_users SET password = CONCAT('bcrypt$', password) "
            "WHERE password LIKE '$2%%'"
        )
        print(f"Prefixed {cursor.rowcount} hash(es).")

    return 0


if __name__ == "__main__":
    sys.exit(main())
