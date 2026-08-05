"""Create the private storage tree.

Run once after deployment, and by the dev setup, so an upload works on a
fresh clone instead of failing on a missing directory.
"""

from django.conf import settings
from django.core.management.base import BaseCommand

from apps.files.storage import ensure_directories, storage_root


class Command(BaseCommand):
    help = "Create the private storage directories with restrictive permissions."

    def handle(self, *args, **options):
        ensure_directories()

        root = storage_root()
        self.stdout.write(self.style.SUCCESS(f"Storage ready at {root}"))

        # A storage root inside the web root is a data breach waiting for a
        # misconfigured Alias directive. Say so loudly.
        static_root = str(settings.STATIC_ROOT)
        if str(root).startswith(static_root):
            self.stdout.write(
                self.style.ERROR(
                    "PRIVATE_STORAGE_ROOT is inside STATIC_ROOT. Uploaded files would be "
                    "publicly downloadable. Move it outside the web root."
                )
            )
