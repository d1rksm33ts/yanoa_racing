"""Private, server-paced replays through the same parser and feedback engine."""
import copy
import hashlib
import json
import uuid
from pathlib import Path

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from .live_core import ApexAdapter
from .live_models import FollowSession, TimingConnection, TimingRecording, TimingSimulation, TimingTrack
from .live_service import ingest, publish

class SimulationLimitError(ValueError):
    pass


SPEEDS = (0.25, 0.5, 1, 2, 5, 10, 20)


def recording_path(recording):
    root = Path(settings.LIVECOACH_RECORDINGS_DIR).resolve()
    path = Path(recording.path).resolve()
    if root not in path.parents or not path.is_file():
        raise ValueError("Opname niet beschikbaar in de opnamebibliotheek.")
    return path


def index_recording(path, name):
    adapter = ApexAdapter()
    segments = []
    current = None
    digest = hashlib.sha256()
    last_offset = 0
    with path.open("rb") as source:
        while True:
            begin = source.tell()
            line = source.readline()
            if not line:
                break
            digest.update(line)
            if not line.endswith(b"\n"):
                raise ValueError("Importeer alleen een volledig afgesloten opname.")
            event = json.loads(line)
            old_title = adapter.state["title"]
            adapter.apply(event)
            last_offset = event["offsetMs"]
            if current is not None and adapter.state["title"] != old_title:
                current.update(endByte=begin, endMs=last_offset)
                current = None
            if current is None and adapter.supported and adapter.entrants() and adapter.state["title"]:
                current = {"title": adapter.state["title"], "startMs": last_offset,
                           "byteOffset": source.tell(), "endByte": 0, "endMs": last_offset,
                           "state": copy.deepcopy(adapter.state), "drivers": adapter.entrants()}
                segments.append(current)
        if current is not None:
            current.update(endByte=source.tell(), endMs=last_offset)
    if not segments:
        raise ValueError("Geen ondersteunde sessies gevonden in deze opname.")
    existing = TimingRecording.objects.filter(path=str(path.resolve())).first()
    if existing and existing.checksum == digest.hexdigest():
        return existing
    if existing and TimingSimulation.objects.filter(recording=existing).exists():
        raise ValueError("Gebruik voor een gewijzigde opname een nieuwe bestandsnaam; bestaande simulaties behouden hun bron.")
    return TimingRecording.objects.update_or_create(path=str(path.resolve()), defaults={
        "name": name, "checksum": digest.hexdigest(), "segments": segments,
    })[0]


def simulation_data(sim):
    segment = sim.recording.segments[sim.segment]
    return {"id": str(sim.pk), "trackId": sim.track_id, "recording": sim.recording.name,
            "title": segment["title"], "state": sim.state, "speed": sim.speed,
            "positionMs": sim.position_ms, "durationMs": max(0, segment["endMs"] - segment["startMs"]),
            "error": sim.error}


@transaction.atomic
def create_simulation(owner, recording, segment_index, request_id):
    existing = TimingSimulation.objects.filter(owner=owner, request_id=request_id).first()
    if existing:
        return existing
    segment = recording.segments[segment_index]
    path = recording_path(recording)
    with path.open("rb") as source:
        checksum = hashlib.file_digest(source, "sha256").hexdigest()
    if checksum != recording.checksum:
        raise ValueError("De opname is gewijzigd; laat de bibliotheek opnieuw indexeren.")
    if TimingSimulation.objects.filter(owner=owner).exclude(state__in=["stopped", "finished", "error"]).count() >= 3:
        raise SimulationLimitError("Je hebt drie actieve simulaties. Open Een opname simuleren en kies Stop deze simulatie bij een opname om plaats vrij te maken.")
    track = TimingTrack.objects.create(owner=owner, slug="sim-" + uuid.uuid4().hex[:20],
        name="Simulatie · " + segment["title"][:75], source_id="goodwill" if "goodwill" in recording.name.casefold() else "replay", mode="replay",
        connection="connected", worker_at=timezone.now(), title=segment["title"],
        parser_state=copy.deepcopy(segment["state"]), entrants=segment["drivers"],
        capabilities={"laps": True, "sectors": bool(ApexAdapter(segment["state"]).sector_ids()), "sectorIds": ApexAdapter(segment["state"]).sector_ids(), "validity": "unknown"})
    sim = TimingSimulation.objects.create(owner=owner, track=track, recording=recording,
        segment=segment_index, byte_offset=segment["byteOffset"], request_id=request_id)
    TimingConnection.objects.create(owner=owner, track=track, enabled=True)
    return sim


def target_position(sim, now):
    duration = max(0, sim.recording.segments[sim.segment]["endMs"] - sim.recording.segments[sim.segment]["startMs"])
    elapsed = max(0, (now - sim.anchor_at).total_seconds() * 1000 * sim.speed) if sim.state == "playing" and sim.anchor_at else 0
    return min(duration, sim.anchor_ms + int(elapsed))


@transaction.atomic
def tick(sim_id, now=None):
    now = now or timezone.now()
    sim = TimingSimulation.objects.select_for_update(of=("self",)).select_related("recording").get(pk=sim_id)
    if sim.state not in {"paused", "playing"}:
        return
    TimingTrack.objects.filter(pk=sim.track_id).update(worker_at=now)
    if sim.state != "playing":
        return
    segment = sim.recording.segments[sim.segment]
    target = target_position(sim, now)
    done = False
    with recording_path(sim.recording).open("rb") as source:
        source.seek(sim.byte_offset)
        for _ in range(100):
            begin = source.tell()
            if begin >= segment["endByte"]:
                done = True
                break
            line = source.readline()
            if not line:
                done = True
                break
            event = json.loads(line)
            position = max(0, event["offsetMs"] - segment["startMs"])
            if position > target:
                break
            sim.byte_offset = source.tell()
            event["originalReceivedAt"] = event["receivedAt"]
            event["receivedAt"] = now.isoformat()
            # No live WebSocket is involved. Reuse precisely the live ingest path.
            ingest(sim.track_id, f"sim-{sim.pk.hex}-{sim.run}", event)
        if sim.byte_offset >= segment["endByte"]:
            done = True
    sim.position_ms = target
    if done and target >= max(0, segment["endMs"] - segment["startMs"]):
        sim.state = "finished"
        TimingTrack.objects.filter(pk=sim.track_id).update(connection="finished")
    sim.save(update_fields=["byte_offset", "position_ms", "state"])


@transaction.atomic
def control(sim_id, owner, action, speed=None):
    sim = TimingSimulation.objects.select_for_update(of=("self",)).select_related("recording").get(pk=sim_id, owner=owner)
    now = timezone.now()
    if action == "restart":
        segment = sim.recording.segments[sim.segment]
        sim.run += 1
        sim.byte_offset, sim.position_ms, sim.anchor_ms = segment["byteOffset"], 0, 0
        sim.anchor_at, sim.state, sim.error = None, "paused", ""
        TimingTrack.objects.filter(pk=sim.track_id).update(parser_state=copy.deepcopy(segment["state"]),
            entrants=segment["drivers"], connection="connected", worker_at=now)
        initial_karts = {entrant["identity"]: entrant["kart"] for entrant in segment["drivers"]}
        for session in FollowSession.objects.select_for_update().filter(track_id=sim.track_id, state="active"):
            for driver in session.drivers.select_for_update():
                driver.block += 1
                driver.best, driver.last = {}, {}
                driver.kart = initial_karts.get(driver.identity, driver.kart)
                driver.save(update_fields=["block", "best", "last", "kart"])
            publish(session, "reset", {"message": "Simulatie herstart; nieuwe referenties, eerdere feedback bewaard."})
    elif action in {"play", "pause", "speed", "stop"}:
        if sim.state not in {"paused", "playing"}:
            raise ValueError("Herstart de afgelopen simulatie om opnieuw af te spelen.")
        # Drain all due events before changing the clock, so pause is an exact boundary.
        if sim.state == "playing":
            for _ in range(100):
                before = sim.byte_offset
                tick(sim.pk, now=now)
                sim.refresh_from_db()
                if sim.byte_offset == before or sim.state == "finished":
                    break
        sim.anchor_ms = sim.position_ms
        sim.anchor_at = now
        if action == "speed":
            if speed not in SPEEDS:
                raise ValueError("Ongeldige afspeelsnelheid.")
            sim.speed = speed
        elif action == "stop":
            sim.state = "stopped"
            TimingTrack.objects.filter(pk=sim.track_id).update(connection="stopped")
            for session in FollowSession.objects.select_for_update().filter(track_id=sim.track_id, state="active"):
                session.state, session.stopped_at = "stopped", now
                session.save(update_fields=["state", "stopped_at"])
                publish(session, "stop", {"message": "Simulatie gestopt en volgsessie bewaard."})
        elif sim.state != "finished":
            sim.state = "playing" if action == "play" else "paused"
    else:
        raise ValueError("Onbekende simulatieactie.")
    sim.save()
    return sim
