from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from www.live_simulation import index_recording


class Command(BaseCommand):
    help = "Register a finished NDJSON recording from the read-only replay library."

    def add_arguments(self, parser):
        parser.add_argument("filename")
        parser.add_argument("--name", required=True)

    def handle(self, *args, **options):
        root = Path(settings.LIVECOACH_RECORDINGS_DIR).resolve()
        path = (root / options["filename"]).resolve()
        if root not in path.parents or not path.is_file():
            raise CommandError("Recording must exist inside LIVECOACH_RECORDINGS_DIR")
        try:
            recording = index_recording(path, options["name"])
        except (ValueError, KeyError) as error:
            raise CommandError(str(error)) from error
        self.stdout.write(f"Registered {recording.name}: {len(recording.segments)} sessions, SHA256 {recording.checksum}")
