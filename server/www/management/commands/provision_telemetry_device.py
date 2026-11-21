import hashlib
import os
import secrets
from pathlib import Path

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from www.telemetry_core import identifier
from www.telemetry_models import TelemetryDevice


class Command(BaseCommand):
    help = "Create an isolated telemetry device; write its token once to a new private file."

    def add_arguments(self, parser):
        parser.add_argument("device_id")
        parser.add_argument("--owner", required=True, help="Existing username with Live Coach permission")
        parser.add_argument("--token-file", required=True)

    def handle(self, *args, **options):
        try:
            identifier(options["device_id"])
        except ValueError as exc:
            raise CommandError(str(exc)) from exc
        owner = get_user_model().objects.filter(username=options["owner"], is_active=True).first()
        if owner is None or not owner.has_perm("www.use_livecoach"):
            raise CommandError("Owner must have Live Coach permission")
        if TelemetryDevice.objects.filter(device_id=options["device_id"]).exists():
            raise CommandError("Device already exists; existing credentials were preserved")
        token = secrets.token_urlsafe(32)
        path = Path(options["token_file"])
        created = False
        try:
            with transaction.atomic():
                with os.fdopen(os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "w") as stream:
                    created = True
                    stream.write(token + "\n")
                TelemetryDevice.objects.create(device_id=options["device_id"], owner=owner,
                    token_digest=hashlib.sha256(token.encode()).hexdigest())
        except Exception:
            if created:
                path.unlink(missing_ok=True)
            raise
        self.stdout.write(self.style.SUCCESS("Telemetry device created; token stored in the requested private file."))
