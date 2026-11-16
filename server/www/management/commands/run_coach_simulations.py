import signal
import time
from pathlib import Path

from django.core.management.base import BaseCommand
from django.db import OperationalError
from django.utils import timezone

from www.live_models import TimingSimulation, TimingTrack
from www.live_simulation import tick


class Command(BaseCommand):
    help = "Serve private recording simulations, paced on the server."

    def handle(self, *args, **options):
        stopping = False

        def stop(*_):
            nonlocal stopping
            stopping = True

        for sig in (signal.SIGTERM, signal.SIGINT):
            signal.signal(sig, stop)
        self.stdout.write("Simulation service ready")
        while not stopping:
            Path("/tmp/coach-simulations.heartbeat").touch()
            for sim_id in TimingSimulation.objects.filter(state__in=["paused", "playing"]).values_list("pk", flat=True):
                try:
                    tick(sim_id)
                except OperationalError:
                    # The atomic tick rolled back, including its cursor. A transient
                    # lock/deadlock must not destroy an otherwise valid replay.
                    self.stderr.write(f"Simulation {sim_id}: temporary database error; retrying")
                except Exception as error:
                    TimingSimulation.objects.filter(pk=sim_id).update(state="error", error="Opname kon niet worden afgespeeld.")
                    sim = TimingSimulation.objects.get(pk=sim_id)
                    TimingTrack.objects.filter(pk=sim.track_id).update(connection="error", error="Simulatie onderbroken.", worker_at=timezone.now())
                    self.stderr.write(f"Simulation {sim_id}: {type(error).__name__}")
            time.sleep(0.1)
