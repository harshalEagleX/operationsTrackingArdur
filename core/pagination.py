"""Pagination classes.

Two shapes, chosen by what the data does:

  * StandardPagination — page numbers, for master data and admin tables where
    the user expects to jump to page 7.
  * KeysetPagination — a ``before`` cursor, for append-only streams (messages,
    notifications, work sessions) where OFFSET degrades as history grows.
"""

from __future__ import annotations

from collections import OrderedDict

from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response


class StandardPagination(PageNumberPagination):
    """?page=2&page_size=100

    The envelope matches the success shape the frontend expects everywhere
    else: ``{"ok": true, "data": [...], "meta": {...}}``.
    """

    page_size = 50
    page_size_query_param = "page_size"
    max_page_size = 500

    def get_paginated_response(self, data) -> Response:
        return Response(
            OrderedDict(
                [
                    ("ok", True),
                    ("data", data),
                    (
                        "meta",
                        {
                            "count": self.page.paginator.count,
                            "page": self.page.number,
                            "pages": self.page.paginator.num_pages,
                            "page_size": self.get_page_size(self.request),
                            "next": self.get_next_link(),
                            "previous": self.get_previous_link(),
                        },
                    ),
                ]
            )
        )


class LargePagination(StandardPagination):
    """For report tables that are read in bulk."""

    page_size = 200
    max_page_size = 2000


class KeysetPagination:
    """Cursor pagination on a descending integer primary key.

    ``LIMIT 50 OFFSET 20000`` makes the database walk 20,000 rows before
    returning anything. ``WHERE id < ? ORDER BY id DESC LIMIT 50`` is an index
    seek that costs the same on page 1 and page 400.

    Not a DRF pagination class — it is applied inside ``get_queryset()``,
    because the cursor has to reach the query before it is evaluated::

        def get_queryset(self):
            qs = Message.objects.filter(...).order_by("-id")
            return KeysetPagination.apply(qs, self.request)
    """

    default_limit = 50
    max_limit = 200
    cursor_param = "before"
    limit_param = "limit"

    @classmethod
    def apply(cls, queryset, request, *, field: str = "id"):
        before = request.query_params.get(cls.cursor_param)
        if before:
            try:
                queryset = queryset.filter(**{f"{field}__lt": int(before)})
            except (TypeError, ValueError):
                pass  # a junk cursor returns the newest page, not a 500

        return queryset[: cls.resolve_limit(request)]

    @classmethod
    def resolve_limit(cls, request) -> int:
        try:
            limit = int(request.query_params.get(cls.limit_param, cls.default_limit))
        except (TypeError, ValueError):
            return cls.default_limit
        return max(1, min(limit, cls.max_limit))

    @staticmethod
    def envelope(items, serialized, *, field: str = "id") -> dict:
        """Build the response body, including the cursor for the next page."""
        next_cursor = getattr(items[-1], field) if items else None
        return {
            "ok": True,
            "data": serialized,
            "meta": {
                "count": len(serialized),
                "next_before": next_cursor,
                "has_more": bool(items),
            },
        }
