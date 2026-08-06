"""Provision a population of accounts for scripts/load_test/locustfile.py.

Idempotent and namespaced: every employee_id it creates starts with
``LOAD_TEST_PREFIX`` so a run against a local dev database can be identified
and torn down again with ``cleanup_load_test`` without touching the seeded
demo accounts from ``seed_dev``.

Refuses to run when DEBUG is off, for the same reason seed_dev does — this
creates accounts with a published password.
"""

from __future__ import annotations

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.accounts.models import Employee, User
from apps.masters.models import ClientCode, Project, WorkType
from core.timezone import now_ist

LOAD_TEST_PREFIX = "LOADT"
LOAD_TEST_PASSWORD = "load-test-password-1"  # noqa: S105 — local/dev only, never used in prod

# 50 projects across 15 client codes — wide enough that the load test spreads
# real contention across many rows instead of hammering the same handful.
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
PROJECTS = [
    (f"Load Test — {name}", f"LT{index:03d}")
    for index, name in enumerate(_PROJECT_NAMES, start=1)
] + [
    (f"Load Test — Project {index:03d}", f"LT{index:03d}")
    for index in range(len(_PROJECT_NAMES) + 1, 51)
]

CLIENT_CODES = [
    (f"LT-CC-{index:03d}", PROJECTS[(index - 1) * len(PROJECTS) // 15][0])
    for index in range(1, 16)
]

WORK_TYPES = [
    ("Load Test — Data entry", 45.0),
    ("Load Test — Verification", 60.0),
    ("Load Test — Indexing", 80.0),
    ("Load Test — Quality audit", 30.0),
]


class Command(BaseCommand):
    help = "Provision employees + master data for the concurrent-user load test."

    def add_arguments(self, parser):
        parser.add_argument(
            "--employees", type=int, default=130,
            help="Number of employee accounts to provision (default: 130).",
        )
        parser.add_argument(
            "--supervisors", type=int, default=4,
            help="Number of supervisor accounts to provision (default: 4).",
        )
        parser.add_argument("--force", action="store_true", help="Run even with DEBUG=False.")

    @transaction.atomic
    def handle(self, *args, **options):
        if not settings.DEBUG and not options["force"]:
            raise CommandError(
                "seed_load_test refuses to run with DEBUG=False. Pass --force only "
                "against a database you are certain is not production."
            )

        n_employees = options["employees"]
        n_supervisors = options["supervisors"]

        projects = self._seed_projects()
        client_codes = self._seed_client_codes()
        self._seed_work_types()

        sup_count = self._seed_people(
            prefix="LSUP", count=n_supervisors, role="supervisor", projects=projects
        )
        emp_count = self._seed_people(
            prefix="LEMP", count=n_employees, role="employee", projects=projects
        )

        self.stdout.write(self.style.SUCCESS(
            f"\nProvisioned {sup_count} supervisor(s) and {emp_count} employee(s), "
            f"spread across {len(projects)} projects and {len(client_codes)} client codes.\n"
        ))
        self.stdout.write(f"  emp_id prefix   {LOAD_TEST_PREFIX}\n")
        self.stdout.write(f"  password        {LOAD_TEST_PASSWORD}\n")
        self.stdout.write("  cleanup with    python manage.py cleanup_load_test\n")

    # ── seeders ──────────────────────────────────────────────

    def _seed_projects(self) -> list[str]:
        names = []
        for name, code in PROJECTS:
            Project.objects.get_or_create(
                project_name=name,
                defaults={"project_code": code, "start_date": now_ist().date()},
            )
            names.append(name)
        return names

    def _seed_client_codes(self) -> list[str]:
        codes = []
        for code, project in CLIENT_CODES:
            ClientCode.objects.get_or_create(client_code=code, defaults={"project": project})
            codes.append(code)
        return codes

    def _seed_work_types(self) -> None:
        for name, rate in WORK_TYPES:
            WorkType.objects.get_or_create(work_type=name, defaults={"standard_rate": rate})

    def _seed_people(self, *, prefix: str, count: int, role: str, projects: list[str]) -> int:
        created = 0
        for i in range(1, count + 1):
            emp_id = f"{LOAD_TEST_PREFIX}_{prefix}{i:04d}"
            project = projects[i % len(projects)]

            _, made = Employee.objects.get_or_create(
                employee_id=emp_id,
                defaults={
                    "name": f"Load Test {prefix} {i:04d}",
                    "role": role,
                    "project": project,
                    "status": "active",
                    "date_of_joining": now_ist().date(),
                },
            )
            created += made

            if not User.objects.filter(emp_id=emp_id).exists():
                User.objects.create_user(
                    emp_id=emp_id, password=LOAD_TEST_PASSWORD, name=f"Load Test {prefix} {i:04d}"
                )
        return created
