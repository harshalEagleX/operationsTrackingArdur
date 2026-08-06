"""Master data: work types, projects, client codes, shifts.

Read-for-everyone, write-for-admins — and the referential-safety rule that
makes ``deactivate`` and ``hard_delete`` two different operations.
"""

from __future__ import annotations

import pytest

from apps.masters.models import ClientCode, Project, Shift, WorkType
from apps.masters.services import (
    ClientCodeService,
    ProjectService,
    ShiftService,
    WorkTypeService,
    active_client_codes,
    active_projects,
    active_shifts,
    active_work_types,
)
from core.exceptions import ConflictError, PermissionDeniedError

pytestmark = pytest.mark.django_db


# ── MasterDataService: create / update / deactivate / hard_delete ──

def test_only_an_admin_can_create_master_data(supervisor):
    with pytest.raises(PermissionDeniedError):
        WorkTypeService(actor=supervisor).create({"work_type": "New Type"})


def test_admin_can_create_a_work_type(admin):
    wt = WorkTypeService(actor=admin).create({"work_type": "New Type"})
    assert wt.created_by == admin.emp_id


def test_update_stamps_updated_at(admin, masters):
    before = masters["work_type"].updated_at
    updated = WorkTypeService(actor=admin).update(masters["work_type"], {"description": "x"})
    assert updated.updated_at >= before


def test_deactivate_does_not_hard_delete(admin, masters):
    WorkTypeService(actor=admin).deactivate(masters["work_type"])
    masters["work_type"].refresh_from_db()
    assert masters["work_type"].is_active is False
    assert WorkType.objects.filter(pk=masters["work_type"].pk).exists()


def test_deactivate_is_allowed_even_when_the_row_is_referenced(admin, masters, employee):
    from apps.tracking.models import WorkSession

    WorkSession.objects.create(emp_id=employee.emp_id, work_type=masters["work_type"].work_type)

    WorkTypeService(actor=admin).deactivate(masters["work_type"])  # must not raise
    masters["work_type"].refresh_from_db()
    assert masters["work_type"].is_active is False


def test_hard_delete_a_work_type_not_in_use(admin):
    wt = WorkType.objects.create(work_type="Unused Type")
    WorkTypeService(actor=admin).hard_delete(wt)
    assert not WorkType.objects.filter(pk=wt.pk).exists()


def test_hard_delete_refuses_when_referenced_by_a_work_session(admin, masters, employee):
    from apps.tracking.models import WorkSession

    WorkSession.objects.create(emp_id=employee.emp_id, work_type=masters["work_type"].work_type)

    with pytest.raises(ConflictError):
        WorkTypeService(actor=admin).hard_delete(masters["work_type"])

    assert WorkType.objects.filter(pk=masters["work_type"].pk).exists()


def test_hard_delete_project_checks_work_sessions_by_project_name(admin, masters, employee):
    from apps.tracking.models import WorkSession

    WorkSession.objects.create(emp_id=employee.emp_id, project=masters["project"].project_name)

    with pytest.raises(ConflictError):
        ProjectService(actor=admin).hard_delete(masters["project"])


def test_hard_delete_shift_checks_employees(admin):
    from apps.accounts.models import Employee

    shift = Shift.objects.create(shift_name="Graveyard", start_time="23:00", end_time="07:00")
    Employee.objects.create(employee_id="E900", name="Someone", shift="Graveyard", status="active")

    with pytest.raises(ConflictError):
        ShiftService(actor=admin).hard_delete(shift)


def test_for_model_dispatches_to_the_right_service_class():
    from apps.masters.services import MasterDataService

    assert MasterDataService.for_model(WorkType) is WorkTypeService
    assert MasterDataService.for_model(Project) is ProjectService
    assert MasterDataService.for_model(ClientCode) is ClientCodeService
    assert MasterDataService.for_model(Shift) is ShiftService


# ── cached read helpers ───────────────────────────────────────

def test_active_helpers_exclude_deactivated_rows(masters):
    WorkType.objects.filter(pk=masters["work_type"].pk).update(is_active=False)
    ids = {row["id"] for row in active_work_types()}
    assert masters["work_type"].id not in ids


def test_active_helpers_are_cached_until_a_write_bumps_them(
    django_capture_on_commit_callbacks, admin, masters
):
    active_work_types()  # warm the cache
    with django_capture_on_commit_callbacks(execute=True):
        WorkTypeService(actor=admin).create({"work_type": "Freshly Added"})

    names = {row["work_type"] for row in active_work_types()}
    assert "Freshly Added" in names


def test_active_projects_and_client_codes_and_shifts_shape(masters):
    assert any(p["id"] == masters["project"].id for p in active_projects())
    assert any(c["id"] == masters["client_code"].id for c in active_client_codes())
    assert isinstance(active_shifts(), list)


# ── HTTP: CRUD permissions ─────────────────────────────────────

@pytest.mark.parametrize("path", ["worktypes", "projects", "clientcodes", "shifts"])
def test_everyone_signed_in_can_list_master_data(as_employee, masters, path):
    assert as_employee.get(f"/api/v1/masters/{path}/").status_code == 200


@pytest.mark.parametrize("path", ["worktypes", "projects", "clientcodes", "shifts"])
def test_employee_cannot_write_master_data(as_employee, path):
    assert as_employee.post(f"/api/v1/masters/{path}/", {}).status_code == 403


def test_active_query_param_filters_the_list(as_employee, masters):
    WorkType.objects.filter(pk=masters["work_type"].pk).update(is_active=False)

    response = as_employee.get("/api/v1/masters/worktypes/", {"active": "true"})
    ids = [row["id"] for row in response.data["data"]]
    assert masters["work_type"].id not in ids


def test_admin_create_reject_blank_name(as_admin):
    response = as_admin.post("/api/v1/masters/worktypes/", {"work_type": "   "})
    assert response.status_code == 400


def test_admin_create_rejects_a_duplicate_name(as_admin, masters):
    response = as_admin.post(
        "/api/v1/masters/worktypes/", {"work_type": masters["work_type"].work_type}
    )
    assert response.status_code == 400


def test_delete_over_http_deactivates_not_hard_deletes(as_admin, masters):
    response = as_admin.delete(f"/api/v1/masters/worktypes/{masters['work_type'].id}/")
    assert response.status_code in (200, 204)

    masters["work_type"].refresh_from_db()
    assert masters["work_type"].is_active is False


def test_restore_endpoint_reactivates(as_admin, masters):
    WorkType.objects.filter(pk=masters["work_type"].pk).update(is_active=False)

    response = as_admin.post(f"/api/v1/masters/worktypes/{masters['work_type'].id}/restore/")

    assert response.status_code == 200
    masters["work_type"].refresh_from_db()
    assert masters["work_type"].is_active is True


def test_purge_endpoint_hard_deletes_when_unused(as_admin):
    wt = WorkType.objects.create(work_type="Purge Me")
    response = as_admin.delete(f"/api/v1/masters/worktypes/{wt.id}/purge/")

    assert response.status_code == 200
    assert not WorkType.objects.filter(pk=wt.pk).exists()


def test_purge_endpoint_refuses_when_in_use(as_admin, masters, employee):
    from apps.tracking.models import WorkSession

    WorkSession.objects.create(emp_id=employee.emp_id, work_type=masters["work_type"].work_type)

    response = as_admin.delete(f"/api/v1/masters/worktypes/{masters['work_type'].id}/purge/")
    assert response.status_code == 409
    assert WorkType.objects.filter(pk=masters["work_type"].pk).exists()


def test_project_end_date_before_start_date_is_rejected(as_admin):
    response = as_admin.post(
        "/api/v1/masters/projects/",
        {"project_name": "Backwards Project", "start_date": "2026-06-01", "end_date": "2026-01-01"},
    )
    assert response.status_code == 400


def test_shift_break_minutes_out_of_range_is_rejected(as_admin):
    response = as_admin.post(
        "/api/v1/masters/shifts/",
        {"shift_name": "Odd Shift", "start_time": "09:00", "end_time": "17:00", "break_minutes": 999},
    )
    assert response.status_code == 400


# ── next-id endpoints ───────────────────────────────────────────

def test_worktype_next_id_starts_at_one(as_employee):
    response = as_employee.get("/api/v1/masters/worktypes/next-id/")
    assert response.data["data"]["next_id"] == "WT-001"


def test_worktype_next_id_increments_from_the_last_row(as_employee):
    WorkType.objects.create(work_type="A", wt_id="WT-007")
    response = as_employee.get("/api/v1/masters/worktypes/next-id/")
    assert response.data["data"]["next_id"] == "WT-008"


def test_project_next_id(as_employee):
    response = as_employee.get("/api/v1/masters/projects/next-id/")
    assert response.data["data"]["next_project_id"] == "PRO-0001"


def test_clientcode_next_id(as_employee):
    response = as_employee.get("/api/v1/masters/clientcodes/next-id/")
    assert response.data["data"]["next_clientcode_id"] == "CC-0001"


# ── worktypes-for-clients ────────────────────────────────────────

def test_worktypes_for_clients_requires_an_admin(as_employee):
    """POST on a BaseMasterViewSet inherits IsAdminOrReadOnly regardless of
    whether the action is a lookup rather than a write — this endpoint is
    POST only because it takes a client_codes list in the body, but it ends
    up admin-gated as a side effect. Pinning the current behaviour; whether
    that's the intended scope is worth a product decision, not a silent fix
    here."""
    response = as_employee.post(
        "/api/v1/masters/clientcodes/worktypes-for-clients/", {"client_codes": ["CC-A"]}
    )
    assert response.status_code == 403


def test_worktypes_for_clients_groups_by_client_code(as_admin):
    ClientCode.objects.create(client_code="CC-A", worktypes="Data entry|Indexing")
    ClientCode.objects.create(client_code="CC-B", worktypes="Verification")

    response = as_admin.post(
        "/api/v1/masters/clientcodes/worktypes-for-clients/", {"client_codes": ["CC-A", "CC-B"]}
    )

    assert response.data["data"]["CC-A"] == ["Data entry", "Indexing"]
    assert response.data["data"]["CC-B"] == ["Verification"]


def test_worktypes_for_clients_with_no_input_returns_empty(as_admin):
    response = as_admin.post("/api/v1/masters/clientcodes/worktypes-for-clients/", {})
    assert response.data["data"] == {}


# ── the bundle endpoint ───────────────────────────────────────

def test_bundle_returns_all_four_lists(as_employee, masters):
    response = as_employee.get("/api/v1/masters/bundle/")

    body = response.data["data"]
    assert set(body) == {"work_types", "projects", "client_codes", "shifts"}
    assert any(row["id"] == masters["project"].id for row in body["projects"])


# ── employee-scoped selection helpers ──────────────────────────

def test_selections_endpoint_returns_the_employees_assignments(as_employee, employee):
    from apps.accounts.models import Employee

    project = Project.objects.create(project_name="Assigned Project", project_id="P1")
    Employee.objects.filter(employee_id=employee.emp_id).update(
        project="P1", client_code="CC-1", work_type="Data entry"
    )

    response = as_employee.get("/api/v1/masters/selections/")

    body = response.data["data"]
    assert body["projects"] == [{"project_id": "P1", "project_name": project.project_name}]
    assert body["client_codes"] == ["CC-1"]
    assert body["work_types"] == ["Data entry"]


def test_selections_endpoint_404s_when_no_employee_record(api, django_user_model):
    """Regression coverage for the same self.error() pattern the signup bug
    had — confirms this call site works now that EnvelopeMixin.error() exists."""
    from apps.accounts.models import User

    orphan = User.objects.create_user(emp_id="NOEMP1", password="x", name="No Employee Row")
    api.force_authenticate(user=orphan)

    response = api.get("/api/v1/masters/selections/")
    assert response.status_code == 404


# ── legacy-compat endpoints ───────────────────────────────────
#
# These four views used to build their own Response({...}) directly instead
# of inheriting EnvelopeMixin, so they broke the "one success shape" contract
# every other endpoint honours — see README. Confirmed safe to fix: the
# frontend's fetch wrapper (static/js/core/api.js `handle()`) only unwraps
# `.data` when an "ok" key is present and otherwise passes the payload
# through unchanged, so callers receive the identical final shape whether
# the backend wraps it or not. Now fixed and enveloped like everything else.

def test_emp_get_projects_is_enveloped(as_employee, masters):
    response = as_employee.get("/api/v1/masters/emp_get_projects/")
    assert response.status_code == 200
    assert response.data["ok"] is True
    assert "projects" in response.data["data"]


def test_emp_get_client_codes_is_enveloped(as_employee):
    Project.objects.create(project_name="P", project_id="P1", client_code="CC-1")
    response = as_employee.post("/api/v1/masters/emp_get_client_codes/", {"projects": ["P1"]})

    assert response.data["ok"] is True
    assert response.data["data"]["client_codes"] == ["CC-1"]


def test_emp_get_worktypes_is_enveloped(as_employee):
    ClientCode.objects.create(client_code="CC-1", worktypes="Data entry")
    response = as_employee.post("/api/v1/masters/emp_get_worktypes/", {"client_code": ["CC-1"]})

    assert response.data["ok"] is True
    assert response.data["data"]["work_types"] == ["Data entry"]


def test_emp_get_shifts_is_enveloped(as_employee):
    Shift.objects.create(shift_name="Morning", start_time="09:00", end_time="18:00")
    response = as_employee.get("/api/v1/masters/emp_get_shifts/")

    assert response.data["ok"] is True
    assert response.data["data"][0]["shift"] == "Morning"


def test_client_codes_for_project_endpoint(as_employee, employee):
    from apps.accounts.models import Employee

    Project.objects.create(project_name="P", project_id="P1", client_code="CC-1|CC-2")
    Employee.objects.filter(employee_id=employee.emp_id).update(client_code="CC-1")

    response = as_employee.get("/api/v1/masters/client_codes_for_project/", {"project": "P1"})
    assert response.data["data"]["client_codes"] == ["CC-1"]


def test_work_types_for_client_code_endpoint(as_employee, employee):
    from apps.accounts.models import Employee

    ClientCode.objects.create(client_code="CC-1", worktypes="Data entry|Indexing")
    Employee.objects.filter(employee_id=employee.emp_id).update(work_type="Data entry")

    response = as_employee.get(
        "/api/v1/masters/work_types_for_client_code/", {"client_code": "CC-1"}
    )
    assert response.data["data"]["work_types"] == ["Data entry"]


def test_masters_endpoints_reject_anonymous_requests(api):
    assert api.get("/api/v1/masters/worktypes/").status_code in (401, 403)
    assert api.get("/api/v1/masters/bundle/").status_code in (401, 403)
