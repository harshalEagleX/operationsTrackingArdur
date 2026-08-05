"""Seed a usable local dataset.

Idempotent — run it as often as you like. Creates master data, three accounts
with known passwords, and a couple of allocations so the screens are not
empty on first run.

Refuses to run when DEBUG is off. Seeding a production database with an
account whose password is printed to stdout would be a very bad afternoon.
"""

from __future__ import annotations

from datetime import time, timedelta

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.accounts.models import Employee, User
from apps.allocations.models import BatchAllocation
from apps.masters.models import ClientCode, Project, Shift, WorkType
from apps.settings_app.services import SettingsService
from core.timezone import now_ist

DEMO_PASSWORD = "opstracking123"

ACCOUNTS = [
    ("ADMIN01", "Priya Sharma", "admin", "Operations"),
    ("SUP01", "Rahul Mehta", "supervisor", "Data Processing"),
    ("EMP01", "Anjali Desai", "employee", "Data Processing"),
    ("EMP02", "Vikram Nair", "employee", "Data Processing"),
]

WORK_TYPES = [
    ("Data entry", "Keying records from scanned documents", 45.0),
    ("Verification", "Second-pass check against the source", 60.0),
    ("Indexing", "Tagging documents for retrieval", 80.0),
    ("Quality audit", "Sampling completed batches", 30.0),
]

PROJECTS = [
    ("Northwind Records", "NWR", "Northwind Ltd"),
    ("Cedar Insurance", "CED", "Cedar Assurance"),
    ("Meridian Claims", "MER", "Meridian Group"),
]

CLIENT_CODES = [
    ("NWR-001", "Northwind Ltd", "Northwind Records"),
    ("CED-114", "Cedar Assurance", "Cedar Insurance"),
    ("MER-207", "Meridian Group", "Meridian Claims"),
]

SHIFTS = [
    ("Morning", time(9, 0), time(18, 0), 45),
    ("Evening", time(14, 0), time(23, 0), 45),
    ("Night", time(22, 0), time(7, 0), 45),
]


class Command(BaseCommand):
    help = "Populate the local database with demo data (development only)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--force",
            action="store_true",
            help="Run even when DEBUG is False. You almost certainly do not want this.",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        if not settings.DEBUG and not options["force"]:
            raise CommandError(
                "seed_dev refuses to run with DEBUG=False. This creates accounts with "
                "a published password. Pass --force only if you are certain."
            )

        self.stdout.write("Seeding development data…\n")

        counts = {
            "work types": self._seed_work_types(),
            "projects": self._seed_projects(),
            "client codes": self._seed_client_codes(),
            "shifts": self._seed_shifts(),
            "employees": self._seed_accounts(),
            "allocations": self._seed_allocations(),
            "settings": SettingsService.seed_defaults(),
        }

        for label, created in counts.items():
            self.stdout.write(f"  {label}: {created} created")

        self.stdout.write(self.style.SUCCESS("\nDone. Sign in at http://localhost:8000/login/\n"))
        self.stdout.write("  Admin       ADMIN01")
        self.stdout.write("  Supervisor  SUP01")
        self.stdout.write("  Employee    EMP01 / EMP02")
        self.stdout.write(f"  Password    {DEMO_PASSWORD}   (all accounts)\n")

    # ── seeders ──────────────────────────────────────────────

    def _seed_work_types(self) -> int:
        created = 0
        for name, description, rate in WORK_TYPES:
            _, made = WorkType.objects.get_or_create(
                work_type=name,
                defaults={"description": description, "standard_rate": rate},
            )
            created += made
        return created

    def _seed_projects(self) -> int:
        created = 0
        for name, code, client in PROJECTS:
            _, made = Project.objects.get_or_create(
                project_name=name,
                defaults={"project_code": code, "client_name": client,
                          "start_date": now_ist().date()},
            )
            created += made
        return created

    def _seed_client_codes(self) -> int:
        created = 0
        for code, client, project in CLIENT_CODES:
            _, made = ClientCode.objects.get_or_create(
                client_code=code,
                defaults={"client_name": client, "project": project},
            )
            created += made
        return created

    def _seed_shifts(self) -> int:
        created = 0
        for name, start, end, breaks in SHIFTS:
            _, made = Shift.objects.get_or_create(
                shift_name=name,
                defaults={"start_time": start, "end_time": end, "break_minutes": breaks},
            )
            created += made
        return created

    def _seed_accounts(self) -> int:
        created = 0
        for emp_id, name, role, department in ACCOUNTS:
            _, made = Employee.objects.get_or_create(
                employee_id=emp_id,
                defaults={
                    "name": name,
                    "role": role,
                    "department": department,
                    "project": PROJECTS[0][0],
                    "shift": SHIFTS[0][0],
                    "email": f"{emp_id.lower()}@example.com",
                    "date_of_joining": now_ist().date(),
                },
            )
            created += made

            if not User.objects.filter(emp_id=emp_id).exists():
                User.objects.create_user(emp_id=emp_id, password=DEMO_PASSWORD, name=name)

        return created

    def _seed_allocations(self) -> int:
        created = 0
        for index, (emp_id, _, role, _) in enumerate(ACCOUNTS):
            if role != "employee":
                continue
            for offset in range(2):
                allocation_id = f"ALLOC-{emp_id}-{offset + 1}"
                _, made = BatchAllocation.objects.get_or_create(
                    allocation_id=allocation_id,
                    defaults={
                        "employee_id": emp_id,
                        "employee_name": ACCOUNTS[index][1],
                        "project": PROJECTS[offset % len(PROJECTS)][0],
                        "client_code": CLIENT_CODES[offset % len(CLIENT_CODES)][0],
                        "work_type": WORK_TYPES[offset % len(WORK_TYPES)][0],
                        "batch": f"BATCH-{offset + 100}",
                        "order_id": f"ORD-{offset + 5000}",
                        "quantity": 250 * (offset + 1),
                        "due_at": now_ist() + timedelta(days=offset + 1),
                        "allocated_by": "SUP01",
                    },
                )
                created += made
        return created
