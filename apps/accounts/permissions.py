"""Account-specific permissions.

Generic role checks live in core/permissions.py; only rules that mention
account concepts belong here.
"""

from __future__ import annotations

from core.permissions import IsAuthenticatedEmployee


class CanManageEmployee(IsAuthenticatedEmployee):
    """Supervisors manage employees; only admins touch other admins.

    Without the second half, a supervisor can edit an admin's record — set
    their own role to admin via a reporting chain, or lock the real admin out.
    """

    message = "Only an administrator can manage an administrator."

    def has_permission(self, request, view) -> bool:
        return super().has_permission(request, view) and request.user.is_supervisor

    def has_object_permission(self, request, view, obj) -> bool:
        if request.user.is_admin:
            return True
        return getattr(obj, "role", "") != "admin"


class CanViewLoginHistory(IsAuthenticatedEmployee):
    """Your own history, or anyone's if you supervise."""

    message = "You can only view your own login history."

    def has_object_permission(self, request, view, obj) -> bool:
        if request.user.is_supervisor:
            return True
        return obj.emp_id == request.user.emp_id
