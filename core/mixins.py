"""ViewSet mixins.

Views stay thin: parse, delegate to a service, render. These mixins carry the
repetitive parts so an individual ViewSet is usually under 40 lines.
"""

from __future__ import annotations

from rest_framework.response import Response


class ServiceMixin:
    """Give a ViewSet a service instance already bound to the acting user.

        class BreakViewSet(ServiceMixin, viewsets.ModelViewSet):
            service_class = BreakService

            def create(self, request):
                brk = self.service.start_break(request.data["break_type"])
                ...
    """

    service_class = None

    def get_service(self):
        if self.service_class is None:
            raise NotImplementedError(
                f"{type(self).__name__} must set service_class or override get_service()."
            )
        return self.service_class(actor=self.request.user)

    @property
    def service(self):
        return self.get_service()


class EnvelopeMixin:
    """Wrap non-paginated successful responses in the standard envelope.

    Paginated responses already carry it (see core/pagination.py), so the
    frontend sees exactly one success shape and exactly one error shape.

    ``ok()`` is the explicit way to build one. ``finalize_response()`` below
    is the backstop: a ModelViewSet's default ``retrieve()``/``update()``/
    ``partial_update()`` return ``Response(serializer.data)`` directly and
    were never wrapped unless a view happened to override them — a real gap
    found by testing every endpoint against the documented contract rather
    than only the ones an existing test already called. Wrapping here once,
    for every response that isn't already enveloped, is what actually makes
    "one success shape" true instead of "true wherever someone remembered."
    """

    def ok(self, data=None, *, status: int = 200, meta: dict | None = None) -> Response:
        body = {"ok": True, "data": data}
        if meta:
            body["meta"] = meta
        return Response(body, status=status)

    def finalize_response(self, request, response, *args, **kwargs):
        response = super().finalize_response(request, response, *args, **kwargs)

        # Errors are already enveloped by core.exception_handler; paginated
        # responses and anything built via ok()/error() already carry "ok".
        # 204 (bare destroy) has no body — nothing to wrap.
        if (
            response.status_code < 400
            and getattr(response, "data", None) is not None
            and not (isinstance(response.data, dict) and "ok" in response.data)
        ):
            response.data = {"ok": True, "data": response.data}

        return response

    def error(
        self, message: str, *, status: int = 400, code: str = "error", details: dict | None = None
    ) -> Response:
        """Wrap an error response in the standard envelope.

        Prefer raising a ``core.exceptions.DomainError`` subclass from the
        service layer — the exception handler builds this same envelope and
        keeps the error path out of the view. This exists for the rare view
        that must return an error without a service call to raise from.
        """
        body = {"ok": False, "error": {"code": code, "message": message, "details": details or {}}}
        return Response(body, status=status)


class ScopedQuerysetMixin:
    """Row-level scoping for list endpoints.

    An object-level permission class runs only on ``get_object()``. Without
    this, ``GET /feedback/`` happily lists every employee's records and the
    permission class never fires. Any ViewSet over per-employee data needs
    both.

    Requires the model's queryset to expose ``visible_to`` — inherit
    ``core.managers.OwnedQuerySet``.
    """

    def get_queryset(self):
        queryset = super().get_queryset()
        visible_to = getattr(queryset, "visible_to", None)
        if visible_to is None:
            raise NotImplementedError(
                f"{type(self).__name__} uses ScopedQuerysetMixin but its queryset has no "
                "visible_to(); inherit core.managers.OwnedQuerySet."
            )
        return visible_to(self.request.user)


class AuditMixin:
    """Stamp created_by / updated_by from the acting user.

    For models inheriting core.models.ActorStampedModel.
    """

    def perform_create(self, serializer):
        serializer.save(
            created_by=self.request.user.emp_id,
            updated_by=self.request.user.emp_id,
        )

    def perform_update(self, serializer):
        serializer.save(updated_by=self.request.user.emp_id)


class SoftDeleteMixin:
    """DELETE marks the row instead of removing it.

    A work session that vanishes changes last month's report retroactively.
    """

    def perform_destroy(self, instance):
        if hasattr(instance, "soft_delete"):
            instance.soft_delete()
        else:
            instance.delete()
