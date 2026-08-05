"""Cache helpers, mostly for master data.

Work types, projects and client codes are read on nearly every page and change
a few times a week. Caching them removes a handful of queries from every
request; the invalidation hook in apps/masters/services.py keeps them honest.
"""

from __future__ import annotations

import functools
import hashlib
import json
from collections.abc import Callable
from typing import Any

from django.core.cache import cache

MASTER_DATA_TTL = 60 * 15
SHORT_TTL = 60
VERSION_KEY = "cache:version:{namespace}"


def _version(namespace: str) -> int:
    """Namespace version counter.

    Bumping the version orphans every key in that namespace at once, which is
    both faster and more reliable than trying to enumerate and delete keys —
    especially with a Redis instance you should not be running KEYS against.
    """
    return cache.get_or_set(VERSION_KEY.format(namespace=namespace), 1, None)


def bump(namespace: str) -> int:
    """Invalidate a whole namespace."""
    key = VERSION_KEY.format(namespace=namespace)
    try:
        return cache.incr(key)
    except ValueError:
        cache.set(key, 1, None)
        return 1


def make_key(namespace: str, *parts: Any) -> str:
    raw = ":".join(str(p) for p in parts)
    if len(raw) > 150:
        raw = hashlib.sha256(raw.encode()).hexdigest()
    return f"{namespace}:v{_version(namespace)}:{raw}"


def get_or_set(namespace: str, key_parts: tuple, producer: Callable[[], Any],
               ttl: int = MASTER_DATA_TTL) -> Any:
    key = make_key(namespace, *key_parts)
    value = cache.get(key)
    if value is None:
        value = producer()
        cache.set(key, value, ttl)
    return value


def cached(namespace: str, ttl: int = MASTER_DATA_TTL):
    """Decorator for pure, argument-keyed reads.

        @cached("masters")
        def active_projects() -> list[dict]: ...

        active_projects.invalidate()   # bumps the whole namespace
    """

    def decorator(fn):
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            signature = json.dumps([args, sorted(kwargs.items())], default=str)
            return get_or_set(namespace, (fn.__name__, signature), lambda: fn(*args, **kwargs), ttl)

        wrapper.invalidate = lambda: bump(namespace)
        return wrapper

    return decorator


def invalidate_masters() -> None:
    """Call after any write to worktypes / projects / client codes / shifts."""
    bump("masters")
