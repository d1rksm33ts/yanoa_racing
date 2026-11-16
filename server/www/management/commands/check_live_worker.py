from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from www.live_models import TimingTrack


class Command(BaseCommand):
    help = "Check worker heartbeat, separately from whether a track is racing."

    def add_arguments(self, parser):
        parser.add_argument("--track", required=True)

    def handle(self, *args, **options):
        track = TimingTrack.objects.filter(slug=options["track"]).first()
        if not track or not track.worker_at or (timezone.now() - track.worker_at).total_seconds() > 45:
            raise CommandError("Worker heartbeat missing or stale")
        self.stdout.write(f"Worker alive; source {track.connection}")
