"""Password hashing compatibility with the legacy Flask application.

The preferred path is scripts/migrate_password_hashes.py: prefix the stored
``$2b$...`` values with ``bcrypt$`` once, and Django's own BCryptPasswordHasher
reads them from then on. Django then transparently upgrades each user to
BCryptSHA256 on their next successful login, so within a few weeks everyone is
on the stronger scheme with zero password resets.

The hasher below exists for the case where altering the production table is
not possible during cutover. Prefer the migration; this is the fallback.
"""

from __future__ import annotations

from django.contrib.auth.hashers import BCryptPasswordHasher


class LegacyBCryptHasher(BCryptPasswordHasher):
    """Reads bare ``$2a$/$2b$/$2y$`` hashes with no algorithm prefix.

    To enable, put it first in settings.PASSWORD_HASHERS *and* make
    ``User.password`` return the bare value. Note this leaves you maintaining
    crypto-adjacent code indefinitely, which is why it is not the default.
    """

    algorithm = "bcrypt_legacy"
    library = ("bcrypt", "bcrypt")

    def verify(self, password: str, encoded: str) -> bool:
        if encoded.startswith("$2"):
            bcrypt = self._load_library()
            return bcrypt.checkpw(password.encode("utf-8"), encoded.encode("utf-8"))
        return super().verify(password, encoded)

    def safe_summary(self, encoded: str) -> dict:
        return {"algorithm": self.algorithm, "salt": "********", "hash": "********"}


def is_legacy_bcrypt(encoded: str) -> bool:
    """True for a hash the Flask app wrote and Django cannot yet read."""
    return bool(encoded) and encoded.startswith("$2")


def prefix_legacy_hash(encoded: str) -> str:
    """``$2b$12$...`` → ``bcrypt$$2b$12$...``  (idempotent)."""
    return f"bcrypt${encoded}" if is_legacy_bcrypt(encoded) else encoded
