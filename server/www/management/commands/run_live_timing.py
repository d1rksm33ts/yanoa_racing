import json
import os
import queue
import signal
import subprocess
import threading
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import connection
from django.utils import timezone

from www.live_models import TimingTrack, TimingPacket
from www.live_service import SOURCES, ingest, seed_tracks


class Command(BaseCommand):
    help = "Run a shared server-side APEX recorder and feedback worker for one track."

    def add_arguments(self, parser):
        parser.add_argument("--track", required=True, choices=sorted(SOURCES))

    def handle(self, *args, **options):
        seed_tracks()
        track = TimingTrack.objects.get(slug=options["track"])
        root = Path(os.getenv("LIVECOACH_DATA_DIR", settings.BASE_DIR / "live-data")) / track.slug
        root.mkdir(parents=True, exist_ok=True)
        # Prevent two workers ingesting the same live source on shared PostgreSQL.
        lock_file = None
        if connection.vendor == "postgresql":
            with connection.cursor() as cursor:
                cursor.execute("SELECT pg_try_advisory_lock(168521, %s)", [track.pk])
                if not cursor.fetchone()[0]:
                    raise CommandError("A worker already owns this track")
        else:
            import fcntl
            lock_file = (root / "worker.lock").open("w")
            try:
                fcntl.flock(lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as exc:
                raise CommandError("A worker already owns this track") from exc
        env = {**os.environ, "SOURCE_ID": track.source_id, "DATA_DIR": str(root),
               "RECORDING_NAME": f"Live Coach — {track.name} — {timezone.now().isoformat()}"}
        TimingTrack.objects.filter(pk=track.pk).update(connection="recovering", worker_at=None)
        # Recover raw events that reached disk but not the transaction before a crash.
        for raw in sorted(root.glob("*.ndjson"), key=lambda p: p.stat().st_mtime):
            recover_raw(track.pk, raw)
        child = subprocess.Popen([os.getenv("NODE_BINARY", "node"), str(settings.BASE_DIR / "timing/bridge.mjs")],
                                 stdout=subprocess.PIPE, text=True, encoding="utf8", env=env)
        inbox = queue.Queue(maxsize=100)

        def receive():
            try:
                for line in child.stdout:
                    inbox.put(line)
            finally:
                inbox.put(None)

        threading.Thread(target=receive, daemon=True).start()
        stopping = False

        def stop(*_):
            nonlocal stopping
            stopping = True

        previous = {s: signal.signal(s, stop) for s in (signal.SIGTERM, signal.SIGINT)}
        TimingTrack.objects.filter(pk=track.pk).update(connection="connecting", error="", worker_at=timezone.now())
        self.stdout.write(f"Recording and following {track.name}")
        try:
            while not stopping:
                try:
                    line = inbox.get(timeout=1)
                except queue.Empty:
                    if child.poll() is not None:
                        raise CommandError("Timing transport exited")
                    continue
                if line is None:
                    raise CommandError("Timing transport closed")
                message = json.loads(line)
                if "packet" in message:
                    ingest(track.pk, message["recordingId"], message["packet"])
                elif "status" in message:
                    status = message["status"]
                    TimingTrack.objects.filter(pk=track.pk).update(worker_at=timezone.now(),
                        connection=status["connection"], error=(status["lastError"] or "")[:300])
        except Exception:
            TimingTrack.objects.filter(pk=track.pk).update(connection="error", error="Worker gestopt door een fout; controleer serverlogs.")
            raise
        finally:
            child.terminate()
            try:
                child.wait(timeout=20)
            except subprocess.TimeoutExpired:
                child.kill()
                child.wait()
            child.stdout.close()
            TimingTrack.objects.filter(pk=track.pk).update(connection="offline", worker_at=timezone.now())
            for sig, handler in previous.items():
                signal.signal(sig, handler)
            if lock_file:
                lock_file.close()
            if connection.vendor == "postgresql":
                with connection.cursor() as cursor:
                    cursor.execute("SELECT pg_advisory_unlock(168521, %s)", [track.pk])


def recover_raw(track_id, raw):
    # Read checkpoints once per recording. Keep holes recoverable instead of
    # assuming the highest sequence implies that every earlier packet committed.
    known = set(TimingPacket.objects.filter(track_id=track_id, key__startswith=raw.stem + ":").values_list("key", flat=True))
    recovered = 0
    with raw.open(encoding="utf8") as saved:
        for line in saved:
            if not line.endswith("\n"):
                break
            packet = json.loads(line)
            key = f"{raw.stem}:{packet['seq']}"
            if key not in known:
                ingest(track_id, raw.stem, packet, recovery=True)
                known.add(key)
                recovered += 1
    return recovered
