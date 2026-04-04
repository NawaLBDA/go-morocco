from __future__ import annotations

from pathlib import Path

from django.conf import settings
from django.core.management import BaseCommand, CommandError, call_command

from apps.core.models import Tour


class Command(BaseCommand):
    help = "Load core catalog seed data (destinations, tours, extras, etc.) if the database is empty."

    def add_arguments(self, parser):
        parser.add_argument(
            "--fixture",
            default="data/seed_core.json",
            help="Path to the fixture JSON (relative to BASE_DIR or absolute).",
        )
        parser.add_argument(
            "--force",
            action="store_true",
            help="Load the fixture even if Tours already exist.",
        )

    def handle(self, *args, **options):
        fixture_arg: str = options["fixture"]
        force: bool = bool(options["force"])

        if not force and Tour.objects.exists():
            self.stdout.write(self.style.SUCCESS("Seed skipped: Tours already exist."))
            return

        base_dir = Path(settings.BASE_DIR)
        fixture_path = Path(fixture_arg)
        if not fixture_path.is_absolute():
            fixture_path = base_dir / fixture_path

        if not fixture_path.exists():
            raise CommandError(f"Seed fixture not found: {fixture_path}")

        self.stdout.write(f"Loading seed fixture: {fixture_path}")
        try:
            call_command("loaddata", str(fixture_path))
        except Exception as exc:
            raise CommandError(f"Failed to load seed data: {exc}") from exc

        self.stdout.write(self.style.SUCCESS("Seed loaded successfully."))
