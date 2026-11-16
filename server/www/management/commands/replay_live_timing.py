import json
import time
import uuid
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from www.live_models import FollowSession, TimingTrack
from www.live_service import ingest


class Command(BaseCommand):
    help = "Replay raw APEX events into an isolated REPLAY track, never into a live track."

    def add_arguments(self, parser):
        parser.add_argument("recording", type=Path)
        parser.add_argument("--speed", type=float, default=1)
        parser.add_argument("--wait-for-session", action="store_true")

    def handle(self, *args, **options):
        if not 0.25 <= options["speed"] <= 100:
            raise CommandError("Speed must be between 0.25 and 100")
        track = TimingTrack.objects.create(slug="replay-" + uuid.uuid4().hex[:16], name="Replay · " + options["recording"].stem[:40], source_id="replay", mode="replay", connection="connected", worker_at=timezone.now())
        self.stdout.write(f"Select {track.name} at /live/ (track {track.pk})")
        previous = None
        waited = False
        try:
            with options["recording"].open(encoding="utf8") as recording:
                for line in recording:
                    if not line.endswith("\n"):
                        break
                    packet = json.loads(line)
                    offset = packet["offsetMs"]
                    delay = max(0, (offset - previous) / 1000 / options["speed"]) if previous is not None else 0
                    deadline = time.monotonic() + delay
                    while time.monotonic() < deadline:
                        TimingTrack.objects.filter(pk=track.pk).update(worker_at=timezone.now())
                        time.sleep(max(0, min(1, deadline - time.monotonic())))
                    previous = offset
                    packet["originalReceivedAt"] = packet["receivedAt"]
                    packet["receivedAt"] = timezone.now().isoformat()
                    ingest(track.pk, track.slug, packet)
                    track.refresh_from_db()
                    if options["wait_for_session"] and track.entrants and not waited:
                        waited = True
                        until = time.monotonic() + 300
                        self.stdout.write("Replay ready; select pilots and start a session within five minutes.")
                        while not FollowSession.objects.filter(track=track, state="active").exists():
                            if time.monotonic() >= until:
                                raise CommandError("No session started")
                            TimingTrack.objects.filter(pk=track.pk).update(worker_at=timezone.now())
                            time.sleep(1)
        finally:
            TimingTrack.objects.filter(pk=track.pk).update(connection="offline", worker_at=timezone.now())
        self.stdout.write("Replay complete; follow sessions remain available in the archive.")
