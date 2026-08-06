"""Remove everything scripts/load_test/ created.

Deletes by emp_id / allocation_id prefix rather than by a time window, so it
is safe to run mid-test-development without sweeping up unrelated data.
"""

from __future__ import annotations

from django.core.management.base import BaseCommand
from django.db import transaction

from core.management.commands.seed_load_test import LOAD_TEST_PREFIX


class Command(BaseCommand):
    help = "Delete all accounts and records created by seed_load_test."

    @transaction.atomic
    def handle(self, *args, **options):
        from apps.accounts.models import Employee, LoginHistory, User
        from apps.allocations.models import BatchAllocation, OrderHistory
        from apps.breaks.models import BreakTime
        from apps.notifications.models import Notification, NotificationPreference
        from apps.tracking.models import Target, WorkSession

        emp_ids = list(
            Employee.objects.filter(employee_id__startswith=LOAD_TEST_PREFIX)
            .values_list("employee_id", flat=True)
        )

        counts = {
            "work sessions": WorkSession.objects.filter(emp_id__in=emp_ids).delete()[0],
            "targets": Target.objects.filter(emp_id__in=emp_ids).delete()[0],
            "breaks": BreakTime.objects.filter(user_id__in=emp_ids).delete()[0],
            "allocations": BatchAllocation.objects.filter(employee_id__in=emp_ids).delete()[0],
            "order history": OrderHistory.objects.filter(employee_id__in=emp_ids).delete()[0],
            "notifications": Notification.objects.filter(recipient_emp_id__in=emp_ids).delete()[0],
            "notification prefs": NotificationPreference.objects.filter(
                emp_id__in=emp_ids
            ).delete()[0],
            "login history": LoginHistory.objects.filter(emp_id__in=emp_ids).delete()[0],
            "users": User.objects.filter(emp_id__in=emp_ids).delete()[0],
            "employees": Employee.objects.filter(employee_id__in=emp_ids).delete()[0],
        }

        for label, n in counts.items():
            self.stdout.write(f"  {label}: {n} deleted")

        self.stdout.write(self.style.SUCCESS(f"\nCleaned up {len(emp_ids)} load-test accounts.\n"))
