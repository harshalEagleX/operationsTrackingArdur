"""Concurrent-user load test for OpsTracking.

Simulates a floor of up to 500 employees who are continuously logged in and
working — starting/pausing/ending work sessions, taking breaks, picking up,
progressing and completing allocated batches, occasionally reassigned or
cancelled — spread across 50 projects and 15 client codes, plus a roster of
supervisors who keep the pipeline fed with new allocations ("orders") at a
rate tunable up to ~3000/day. It is deliberately built against the real
HTTP API (session cookies + CSRF, exactly like a browser) rather than
calling services in-process, because the thing worth measuring is whether
the whole stack — WSGI, DB pool, row locks — holds up, not whether the
Python is fast.

Setup (once):
    # in the project's own venv, against a real (dev) database:
    python manage.py seed_load_test --employees 520 --supervisors 15

Run (in a separate env — this needs `locust`, which the project's pinned
requirements deliberately do not carry):
    conda activate ops-loadtest
    locust -f scripts/load_test/locustfile.py --host http://127.0.0.1:8001 \\
        --headless -u 500 -r 25 -t 5m --csv scripts/load_test/results/run --html scripts/load_test/results/run.html

Point --host at gunicorn (:8001), never at `manage.py runserver` — see
scripts/load_test/README.md for why.

Teardown:
    python manage.py cleanup_load_test

── Scaling to a literal "3000 orders/day" ───────────────────────────────
SupervisorUser.create_order fires roughly once per `order_wait` seconds per
active supervisor. With S supervisors, to average R orders/day:
    order_wait ≈ S * 86400 / R
For S=15, R=3000 → order_wait ≈ 432s. ORDER_WAIT below defaults to a much
shorter interval so a multi-minute test run actually produces observable
throughput; pass LOCUST_ORDER_WAIT_SECONDS=432 to set it to the real value
for a true 24h-equivalent soak run.
"""

from __future__ import annotations

import itertools
import os
import random
import threading

from locust import HttpUser, between, events, task

PREFIX = "LOADT"
PASSWORD = "load-test-password-1"  # noqa: S105 — load-test fixture, not a real credential
N_EMPLOYEES = int(os.environ.get("LOCUST_N_EMPLOYEES", 520))
N_SUPERVISORS = int(os.environ.get("LOCUST_N_SUPERVISORS", 15))
ORDER_WAIT_SECONDS = float(os.environ.get("LOCUST_ORDER_WAIT_SECONDS", 8))

# Must generate byte-for-byte the same catalogue as
# core/management/commands/seed_load_test.py — this process runs in a
# separate conda env with no Django installed, so it cannot import that
# module directly and duplicates the generation instead.
_PROJECT_NAMES = [
    "Northwind Records", "Cedar Insurance", "Meridian Claims", "Solstice Titles",
    "Ashford Legal", "Blue Harbor Logistics", "Crestline Health", "Dune Capital",
    "Everwood Realty", "Falcon Freight", "Granite Municipal", "Harbor Point Bank",
    "Ironwood Utilities", "Junction Retail", "Kestrel Aerospace", "Lakeshore County",
    "Maple Grove ISD", "Nightingale Health", "Overlook Title Co", "Pinecrest Energy",
    "Quarry Ridge Mining", "Riverside Trust", "Summit Underwriters", "Thornwood Estates",
    "Union Depot Rail", "Vantage Point Capital", "Westfield County", "Xenith Data",
    "Yellowstone Ag", "Zephyr Airlines",
]
PROJECTS = [f"Load Test — {name}" for name in _PROJECT_NAMES] + [
    f"Load Test — Project {index:03d}" for index in range(len(_PROJECT_NAMES) + 1, 51)
]
CLIENT_CODES = [f"LT-CC-{index:03d}" for index in range(1, 16)]
WORK_TYPES = [
    "Load Test — Data entry", "Load Test — Verification",
    "Load Test — Indexing", "Load Test — Quality audit",
]
BREAK_TYPES = ["Tea break 1", "Tea break 2", "Rest room", "Technical issue"]

_employee_ids = [f"{PREFIX}_LEMP{i:04d}" for i in range(1, N_EMPLOYEES + 1)]
_supervisor_ids = [f"{PREFIX}_LSUP{i:04d}" for i in range(1, N_SUPERVISORS + 1)]

_lock = threading.Lock()
_employee_pool = itertools.cycle(_employee_ids)
_supervisor_pool = itertools.cycle(_supervisor_ids)
_order_counter = itertools.count(1)


def _next(pool):
    with _lock:
        return next(pool)


class ApiSession:
    """Shared login/CSRF plumbing for both user types."""

    def login(self, emp_id: str) -> bool:
        self.client.get("/login/", name="/login/ [csrf]")
        response = self.client.post(
            "/api/v1/auth/login/",
            json={"emp_id": emp_id, "password": PASSWORD},
            headers=self._csrf_headers(),
            name="/api/v1/auth/login/",
        )
        return response.status_code == 200

    def _csrf_headers(self) -> dict:
        token = self.client.cookies.get("csrftoken", "")
        return {"X-CSRFToken": token, "Referer": self.host}

    def api_get(self, path: str, params: dict | None = None, name: str | None = None):
        return self.client.get(path, params=params, name=name or path)

    def api_post(self, path: str, json: dict | None = None, name: str | None = None,
                 expect: tuple[int, ...] = (200, 201)):
        """POST with fresh CSRF headers. Business-rule conflicts (409/404 from
        a race that another concurrent request already won) are marked as
        successes — they are the system behaving correctly under contention,
        not a defect. Anything else outside `expect` is a real failure."""
        with self.client.post(
            path, json=json or {}, headers=self._csrf_headers(),
            name=name or path, catch_response=True,
        ) as response:
            if response.status_code in expect:
                response.success()
            elif response.status_code in (404, 409):
                response.success()  # expected contention, not a bug
            else:
                response.failure(f"unexpected {response.status_code}: {response.text[:200]}")
            return response


class EmployeeUser(ApiSession, HttpUser):
    """One continuously-working floor employee."""

    # 35:1 against SupervisorUser's weight=1 approximates the provisioned
    # 520:15 employee:supervisor ratio at any -u count Locust is run with.
    weight = 35
    wait_time = between(1, 4)

    def on_start(self):
        self.emp_id = _next(_employee_pool)
        self.open_session_id = None
        self.on_break = False
        if not self.login(self.emp_id):
            self.environment.runner.quit()

    # ── the main work loop ───────────────────────────────────

    @task(10)
    def work_cycle(self):
        current = self.api_get("/api/v1/tracking/sessions/current/", name="/tracking/sessions/current/")
        session = None
        if current.status_code == 200:
            session = current.json().get("data")

        if session is None:
            session = self._pick_up_or_start_work()
            if session is None:
                return
        session_id = session["id"]

        # Small chance of a pause/resume cycle before finishing — mirrors an
        # employee stepping away mid-task.
        if random.random() < 0.15:
            self.api_post(f"/api/v1/tracking/sessions/{session_id}/pause/",
                           name="/tracking/sessions/{id}/pause/")
            self.api_post(f"/api/v1/tracking/sessions/{session_id}/resume/",
                           name="/tracking/sessions/{id}/resume/")

        # Most cycles end the session (a unit of work completes); some leave
        # it open to be picked up again next cycle, like a real shift.
        if random.random() < 0.7:
            work_units = random.randint(1, 25)
            self.api_post(
                f"/api/v1/tracking/sessions/{session_id}/end/",
                json={"work_units": work_units, "pages": random.randint(1, 50)},
                name="/tracking/sessions/{id}/end/",
            )
            allocation_id = session.get("allocation_id")
            if allocation_id:
                self._progress_allocation(allocation_id, work_units)

    def _pick_up_or_start_work(self):
        mine = self.api_get("/api/v1/allocations/mine/", name="/allocations/mine/")
        allocation = None
        if mine.status_code == 200:
            open_allocations = mine.json().get("data") or []
            if open_allocations:
                allocation = random.choice(open_allocations)

        if allocation:
            if allocation["status"] == "pending":
                self.api_post(
                    f"/api/v1/allocations/{allocation['allocation_id']}/status/",
                    json={"status": "in_progress"},
                    name="/allocations/{id}/status/",
                )
            payload = {
                "project": allocation["project"] or random.choice(PROJECTS),
                "work_type": allocation["work_type"] or random.choice(WORK_TYPES),
                "client_code": allocation["client_code"],
                "batch": allocation["batch"],
                "allocation_id": allocation["allocation_id"],
            }
        else:
            # Ad-hoc work against no particular allocation — different
            # project/client each time, same as an employee picking their
            # next queue item off a shared board.
            payload = {
                "project": random.choice(PROJECTS),
                "work_type": random.choice(WORK_TYPES),
                "client_code": random.choice(CLIENT_CODES),
                "batch": f"BATCH-{random.randint(1, 999):03d}",
            }

        response = self.api_post(
            "/api/v1/tracking/sessions/", json=payload, name="/tracking/sessions/ [start]"
        )
        if response.status_code == 201:
            return response.json()["data"]
        return None

    def _progress_allocation(self, allocation_id: str, units: int):
        self.api_post(
            f"/api/v1/allocations/{allocation_id}/status/",
            json={"status": "completed", "completed_quantity": units},
            name="/allocations/{id}/status/",
        )

    # ── breaks ────────────────────────────────────────────────

    @task(2)
    def take_a_break(self):
        current = self.api_get("/api/v1/breaks/current/", name="/breaks/current/")
        if current.status_code == 200 and current.json().get("data"):
            self.api_post("/api/v1/breaks/end/", name="/breaks/end/")
            return

        self.api_post(
            "/api/v1/breaks/",
            json={"break_type": random.choice(BREAK_TYPES)},
            name="/breaks/ [start]",
        )

    # ── the bits that stay lightweight and constant — dashboard, inbox ──

    @task(6)
    def check_dashboard(self):
        self.api_get("/api/v1/tracking/summary/", name="/tracking/summary/")

    @task(4)
    def check_notifications(self):
        """The inbox must keep working under load — this is the assertion
        surface for 'notifications must work' during the run."""
        self.api_get("/api/v1/notifications/unread-count/", name="/notifications/unread-count/")
        if random.random() < 0.3:
            self.api_post("/api/v1/notifications/read/", json={"ids": []}, name="/notifications/read/")


class SupervisorUser(ApiSession, HttpUser):
    """Keeps the pipeline fed: creates allocations ("orders"), reassigns and
    occasionally cancels them, sets targets, watches the floor."""

    weight = 1
    wait_time = between(ORDER_WAIT_SECONDS * 0.5, ORDER_WAIT_SECONDS * 1.5)

    def on_start(self):
        self.emp_id = _next(_supervisor_pool)
        self.created_orders: list[str] = []  # allocation_ids this instance made
        if not self.login(self.emp_id):
            self.environment.runner.quit()

    @task(10)
    def create_order(self):
        n = next(_order_counter)
        target_employee = random.choice(_employee_ids)
        # Independent choices — PROJECTS (50) and CLIENT_CODES (15) are not
        # the same length, so indexing them by the same value is a bug in
        # its own right (this file used to do exactly that).
        project = random.choice(PROJECTS)
        client_code = random.choice(CLIENT_CODES)
        allocation_id = f"{PREFIX}-ORD-{self.emp_id}-{n:06d}"

        response = self.api_post(
            "/api/v1/allocations/",
            json={
                "allocation_id": allocation_id,
                "employee_id": target_employee,
                "project": project,
                "client_code": client_code,
                "work_type": random.choice(WORK_TYPES),
                "batch": f"BATCH-{random.randint(1, 999):03d}",
                "order_id": f"{PREFIX}-ORDID-{n:06d}",
                "quantity": random.randint(20, 300),
                "priority": random.choice(["low", "normal", "normal", "high"]),
            },
            name="/allocations/ [create order]",
        )
        if response.status_code == 201:
            self.created_orders.append(allocation_id)
            if len(self.created_orders) > 200:  # bounded — this is a long-running process
                self.created_orders = self.created_orders[-200:]

    @task(2)
    def reassign_an_order(self):
        """Work moves between people — a supervisor rebalancing the floor."""
        if not self.created_orders:
            return
        allocation_id = random.choice(self.created_orders)
        new_owner = random.choice(_employee_ids)
        self.api_post(
            f"/api/v1/allocations/{allocation_id}/reassign/",
            json={"employee_id": new_owner},
            name="/allocations/{id}/reassign/",
        )

    @task(1)
    def cancel_an_order(self):
        """A batch turns out to be a duplicate or the client pulls it."""
        if not self.created_orders:
            return
        allocation_id = self.created_orders.pop(random.randrange(len(self.created_orders)))
        self.api_post(
            f"/api/v1/allocations/{allocation_id}/cancel/",
            json={"reason": "Load-test cancellation"},
            name="/allocations/{id}/cancel/",
        )

    @task(2)
    def check_order_history(self):
        """The audit trail — a supervisor checking what happened to a batch."""
        if not self.created_orders:
            return
        allocation_id = random.choice(self.created_orders)
        self.api_get(
            f"/api/v1/allocations/{allocation_id}/history/", name="/allocations/{id}/history/"
        )

    @task(3)
    def review_the_allocation_board(self):
        """The supervisor's worklist view: open and overdue batches."""
        self.api_get("/api/v1/allocations/", {"open": "true"}, name="/allocations/ [open]")
        if random.random() < 0.4:
            self.api_get(
                "/api/v1/allocations/", {"overdue": "true"}, name="/allocations/ [overdue]"
            )

    @task(1)
    def set_a_target(self):
        from datetime import date

        self.api_post(
            "/api/v1/tracking/targets/",
            json={
                "emp_id": random.choice(_employee_ids),
                "target_date": date.today().isoformat(),
                "target_units": random.randint(50, 400),
                "project": random.choice(PROJECTS),
            },
            name="/tracking/targets/ [set]",
        )

    @task(3)
    def watch_the_floor(self):
        self.api_get("/api/v1/tracking/sessions/active/", name="/tracking/sessions/active/")
        self.api_get("/api/v1/presence/", name="/presence/")
        self.api_get("/api/v1/reports/metrics/", name="/reports/metrics/")


@events.test_start.add_listener
def _on_start(environment, **kwargs):
    print(
        f"\nLoad test starting: {N_EMPLOYEES} employees, {N_SUPERVISORS} supervisors, "
        f"{len(PROJECTS)} projects, {len(CLIENT_CODES)} client codes. "
        f"order_wait≈{ORDER_WAIT_SECONDS}s/supervisor.\n"
    )
