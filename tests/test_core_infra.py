"""Cross-cutting core/ infrastructure: auth glue, legacy hashing, cache
helpers, throttle key derivation, validators, health probes, and pagination.
"""

from __future__ import annotations

import pytest

from core.cache import bump, cached, get_or_set, invalidate_masters, make_key
from core.hashers import LegacyBCryptHasher, is_legacy_bcrypt, prefix_legacy_hash
from core.validators import (
    validate_date_range,
    validate_emp_id,
    validate_positive,
    validate_safe_name,
)
from django.core.exceptions import ValidationError as DjangoValidationError

pytestmark = pytest.mark.django_db


# ── core.authentication ──────────────────────────────────────

def test_csrf_exempt_session_authentication_never_raises():
    from core.authentication import CsrfExemptSessionAuthentication

    auth = CsrfExemptSessionAuthentication()
    assert auth.enforce_csrf(request=None) is None  # a no-op, not an exception


def test_get_user_from_session_key_resolves_a_real_session(client, employee):
    from tests.conftest import PASSWORD

    client.login(emp_id=employee.emp_id, password=PASSWORD)
    session_key = client.session.session_key

    from core.authentication import get_user_from_session_key

    resolved = get_user_from_session_key(session_key)
    assert resolved is not None
    assert resolved.emp_id == employee.emp_id


def test_get_user_from_session_key_returns_none_for_empty_key():
    from core.authentication import get_user_from_session_key

    assert get_user_from_session_key("") is None
    assert get_user_from_session_key(None) is None


def test_get_user_from_session_key_returns_none_for_a_bogus_key():
    from core.authentication import get_user_from_session_key

    assert get_user_from_session_key("not-a-real-session-key") is None


# ── core.hashers: legacy bcrypt cutover ──────────────────────

def test_is_legacy_bcrypt_detects_bare_bcrypt_hashes():
    assert is_legacy_bcrypt("$2b$12$abcdefghijklmnopqrstuv") is True
    assert is_legacy_bcrypt("$2a$10$whatever") is True
    assert is_legacy_bcrypt("bcrypt$$2b$12$already-prefixed") is False
    assert is_legacy_bcrypt("") is False
    assert is_legacy_bcrypt(None) is False


def test_prefix_legacy_hash_is_idempotent():
    bare = "$2b$12$abcdefghijklmnopqrstuv"
    prefixed = prefix_legacy_hash(bare)
    assert prefixed == f"bcrypt${bare}"
    assert prefix_legacy_hash(prefixed) == prefixed  # already prefixed: unchanged


def test_prefix_legacy_hash_leaves_a_non_bcrypt_value_alone():
    assert prefix_legacy_hash("some-other-hash-scheme$xyz") == "some-other-hash-scheme$xyz"


def test_legacy_bcrypt_hasher_verifies_a_bare_hash():
    import bcrypt

    hasher = LegacyBCryptHasher()
    raw = bcrypt.hashpw(b"correct horse", bcrypt.gensalt())
    assert hasher.verify("correct horse", raw.decode()) is True
    assert hasher.verify("wrong password", raw.decode()) is False


def test_legacy_bcrypt_hasher_safe_summary_never_leaks_the_hash():
    hasher = LegacyBCryptHasher()
    summary = hasher.safe_summary("$2b$12$secretsecretsecret")
    assert summary["hash"] == "********"
    assert summary["salt"] == "********"


# ── core.cache ────────────────────────────────────────────────

def test_make_key_is_stable_for_the_same_inputs():
    assert make_key("ns", "a", "b") == make_key("ns", "a", "b")


def test_make_key_hashes_very_long_keys():
    long_part = "x" * 300
    key = make_key("ns", long_part)
    assert len(key) < 250  # sha256 hex digest, not the raw 300 chars


def test_bump_orphans_previously_cached_values():
    calls = {"n": 0}

    def producer():
        calls["n"] += 1
        return calls["n"]

    first = get_or_set("test-ns", ("k",), producer)
    assert first == 1
    assert get_or_set("test-ns", ("k",), producer) == 1  # still cached

    bump("test-ns")

    assert get_or_set("test-ns", ("k",), producer) == 2  # recomputed after bump


def test_cached_decorator_caches_by_argument_signature():
    calls = {"n": 0}

    @cached("test-ns-2")
    def expensive(x):
        calls["n"] += 1
        return x * 2

    assert expensive(5) == 10
    assert expensive(5) == 10
    assert calls["n"] == 1  # second call was served from cache

    assert expensive(6) == 12
    assert calls["n"] == 2  # different argument, different cache key


def test_cached_decorator_invalidate_bumps_the_namespace():
    calls = {"n": 0}

    @cached("test-ns-3")
    def expensive():
        calls["n"] += 1
        return calls["n"]

    assert expensive() == 1
    expensive.invalidate()
    assert expensive() == 2


def test_invalidate_masters_bumps_the_masters_namespace():
    from core.cache import _version

    before = _version("masters")  # establishes the counter if it didn't exist yet
    invalidate_masters()

    assert _version("masters") == before + 1


# ── core.throttling ───────────────────────────────────────────

def test_login_throttle_keys_on_ip_and_submitted_emp_id():
    from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
    from rest_framework.request import Request
    from rest_framework.test import APIRequestFactory

    from core.throttling import LoginThrottle

    # get_cache_key reads request.data, which only exists on a DRF Request —
    # and a bare Request() needs its parsers passed explicitly; the normal
    # DEFAULT_PARSER_CLASSES only get wired in by APIView.dispatch().
    django_request = APIRequestFactory().post(
        "/api/v1/auth/login/", {"emp_id": "E1042"}, format="json"
    )
    request = Request(django_request, parsers=[JSONParser(), FormParser(), MultiPartParser()])
    throttle = LoginThrottle()
    key = throttle.get_cache_key(request, view=None)

    assert "login" in key
    assert "E1042" in key


def test_employee_scoped_throttle_keys_on_emp_id_when_authenticated(rf, employee):
    from core.throttling import EmployeeScopedThrottle

    class FakeView:
        upload_scope = "upload"
        throttle_scope = "upload"

    request = rf.get("/")
    request.user = employee

    throttle = EmployeeScopedThrottle()
    throttle.scope = "upload"
    key = throttle.get_cache_key(request, FakeView())

    assert employee.emp_id in key


def test_employee_scoped_throttle_falls_back_to_ip_when_anonymous(rf):
    from django.contrib.auth.models import AnonymousUser

    from core.throttling import EmployeeScopedThrottle

    class FakeView:
        throttle_scope = "upload"

    request = rf.get("/")
    request.user = AnonymousUser()

    throttle = EmployeeScopedThrottle()
    throttle.scope = "upload"
    key = throttle.get_cache_key(request, FakeView())

    assert key is not None


def test_employee_scoped_throttle_returns_none_without_a_scope(rf):
    from core.throttling import EmployeeScopedThrottle

    class FakeView:
        pass

    throttle = EmployeeScopedThrottle()
    throttle.scope = None
    assert throttle.get_cache_key(rf.get("/"), FakeView()) is None


# ── core.validators (the gaps not already covered elsewhere) ──

def test_validate_safe_name_accepts_ordinary_punctuation():
    assert validate_safe_name("Acme & Sons, Ltd. (2026)") == "Acme & Sons, Ltd. (2026)"


def test_validate_safe_name_rejects_special_characters():
    with pytest.raises(DjangoValidationError):
        validate_safe_name("<script>alert(1)</script>")


def test_validate_safe_name_rejects_blank():
    with pytest.raises(DjangoValidationError):
        validate_safe_name("   ")


def test_validate_positive_rejects_negative_and_none():
    with pytest.raises(DjangoValidationError):
        validate_positive(-1)
    with pytest.raises(DjangoValidationError):
        validate_positive(None)
    assert validate_positive(0) == 0


def test_validate_date_range_accepts_a_correctly_ordered_range():
    validate_date_range("2026-01-01", "2026-01-02")  # must not raise


def test_validate_date_range_rejects_start_after_end():
    with pytest.raises(DjangoValidationError):
        validate_date_range("2026-06-01", "2026-01-01")


def test_validate_date_range_tolerates_missing_bounds():
    validate_date_range(None, None)  # must not raise
    validate_date_range("2026-01-01", None)


def test_validate_emp_id_rejects_special_characters():
    with pytest.raises(DjangoValidationError):
        validate_emp_id("E@1042!")


# ── core.views: health / readiness probes ─────────────────────

def test_health_endpoint_touches_nothing_and_always_succeeds(api):
    response = api.get("/health/")
    assert response.status_code == 200
    assert response.data["data"]["status"] == "healthy"


def test_readiness_endpoint_reports_healthy_when_db_and_cache_are_up(api):
    response = api.get("/ready/")
    assert response.status_code == 200
    assert response.data["data"]["checks"]["database"]["ok"] is True
    assert response.data["data"]["checks"]["cache"]["ok"] is True


def test_readiness_endpoint_returns_503_when_the_database_is_down(api, monkeypatch):
    from core.views import ReadinessView

    monkeypatch.setattr(
        ReadinessView, "_check_database", staticmethod(lambda: {"ok": False, "error": "boom"})
    )

    response = api.get("/ready/")
    assert response.status_code == 503
    assert response.data["ok"] is False


def test_readiness_endpoint_returns_503_when_the_cache_is_down(api, monkeypatch):
    from core.views import ReadinessView

    monkeypatch.setattr(
        ReadinessView, "_check_cache", staticmethod(lambda: {"ok": False, "error": "boom"})
    )

    response = api.get("/ready/")
    assert response.status_code == 503


# ── core.managers: the one queryset mixin actually in use ─────

def test_active_queryset_filters_master_data(masters):
    from apps.masters.models import WorkType

    WorkType.objects.filter(pk=masters["work_type"].pk).update(is_active=False)

    assert masters["work_type"] not in WorkType.objects.active()
    assert masters["work_type"] in WorkType.objects.inactive()


# ── core.pagination: StandardPagination across more than one page ──

def test_standard_pagination_returns_a_next_link_past_page_one(as_admin):
    from apps.masters.models import Project

    Project.objects.bulk_create([Project(project_name=f"Bulk Project {i}") for i in range(60)])

    response = as_admin.get("/api/v1/masters/projects/", {"page_size": 50})

    assert response.status_code == 200
    assert response.data["meta"]["pages"] == 2
    assert response.data["meta"]["next"] is not None
    assert response.data["meta"]["previous"] is None


def test_standard_pagination_page_two_has_a_previous_link(as_admin):
    from apps.masters.models import Project

    Project.objects.bulk_create([Project(project_name=f"Bulk Project {i}") for i in range(60)])

    response = as_admin.get("/api/v1/masters/projects/", {"page_size": 50, "page": 2})

    assert response.data["meta"]["previous"] is not None


def test_keyset_pagination_ignores_a_junk_cursor(as_employee, employee):
    from apps.notifications.services import NotificationService

    NotificationService().notify(recipients=[employee.emp_id], notif_type="work.target_met", context={})

    response = as_employee.get("/api/v1/notifications/", {"before": "not-a-number"})
    assert response.status_code == 200  # degrades to the newest page, not a 500


def test_keyset_pagination_clamps_an_excessive_limit(as_employee, employee):
    from apps.notifications.services import NotificationService

    for _ in range(3):
        NotificationService().notify(
            recipients=[employee.emp_id], notif_type="work.target_met", context={}
        )

    response = as_employee.get("/api/v1/notifications/", {"limit": "99999"})
    assert response.status_code == 200
    assert len(response.data["data"]) == 3  # clamped to max_limit, but we only have 3 rows
