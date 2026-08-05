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
    """

    def ok(self, data=None, *, status: int = 200, meta: dict | None = None) -> Response:
        body = {"ok": True, "data": data}
        if meta:
            body["meta"] = meta
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
