import json
from pathlib import Path

from django.core.management.base import BaseCommand

from core.backup import build_portal_backup


class Command(BaseCommand):
    help = "Export a JSON backup of portal data (for nightly cron jobs)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--output",
            type=str,
            default="",
            help="Write backup JSON to this file path. Defaults to stdout.",
        )

    def handle(self, *args, **options):
        payload = build_portal_backup()
        output = (options.get("output") or "").strip()

        if output:
            path = Path(output)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
            self.stdout.write(self.style.SUCCESS(f"Backup written to {path}"))
        else:
            self.stdout.write(json.dumps(payload, indent=2))
