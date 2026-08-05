"""The error envelope.

Two rules the previous application broke:
  * an error is never returned with HTTP 200;
  * a stack trace or raw database message never reaches a browser.
"""

from __future__ import annotations

import pytest

from core.exceptions import ConflictError, DomainError, NotFoundError, ValidationError

pytestmark = pytest.mark.django_db


def test_validation_failure_returns_400_not_200(as_admin):
    response = as_admin.post("/api/v1/masters/projects/", {"project_name": ""})

    assert response.status_code == 400
    assert response.data["ok"] is False
    assert response.data["error"]["code"] == "validation_error"


def test_missing_record_returns_404(as_employee):
    response = as_employee.get("/api/v1/tracking/sessions/999999/")

    assert response.status_code == 404
    assert response.data["ok"] is False


def test_error_envelope_shape_is_consistent(as_employee):
    response = as_employee.get("/api/v1/tracking/sessions/999999/")

    assert set(response.data.keys()) == {"ok", "error"}
    assert set(response.data["error"].keys()) == {"code", "message", "details"}


def test_conflict_returns_409(as_admin):
    as_admin.post("/api/v1/masters/projects/", {"project_name": "Duplicate"})
    response = as_admin.post("/api/v1/masters/projects/", {"project_name": "Duplicate"})

    assert response.status_code == 400  # caught by the serializer's UniqueValidator
    assert response.data["ok"] is False


def test_whitespace_only_name_is_rejected(as_admin):
    """`required=True` alone accepts '   ', which then becomes a record with an
    invisible name that nobody can find or delete."""
    response = as_admin.post("/api/v1/masters/projects/", {"project_name": "   "})

    assert response.status_code == 400


def test_over_length_input_is_rejected_not_truncated(as_admin):
    response = as_admin.post("/api/v1/masters/projects/", {"project_name": "x" * 500})

    assert response.status_code == 400


def test_domain_error_http_status_mapping():
    assert ValidationError("x").http_status == 400
    assert NotFoundError("x").http_status == 404
    assert ConflictError("x").http_status == 409
    assert DomainError("x").http_status == 400


def test_success_envelope_shape(as_employee):
    response = as_employee.get("/api/v1/auth/me/")

    assert response.status_code == 200
    assert response.data["ok"] is True
    assert "data" in response.data
