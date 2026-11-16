"""Transactional application boundary shared by the worker, HTTP UI and replay."""
import hashlib
import re
from datetime import datetime

from django.db import connection, transaction
from django.utils import timezone

from .live_pit import forecast, settings_for
from .live_core import ApexAdapter, delta_feedback, present_feedback
from .live_models import CoachEvent, FollowDriver, FollowSession, TimingPacket, TimingTrack

SOURCES = {
    "agadir": ("Maroc Racing Kart Agadir", "wss://live-data.apex-timing.com:8023"),
    "spa": ("Spa-Francorchamps", "wss://live-data.apex-timing.com:9723"),
    "goodwill": ("Goodwill Karting", "wss://live-data.apex-timing.com:9573"),
    "campillos": ("Karting Campillos", "wss://live-data.apex-timing.com:9373"),
}


def seed_tracks():
    for slug, (name, _) in SOURCES.items():
        TimingTrack.objects.get_or_create(slug=slug, defaults={"name": name, "source_id": slug})


def publish(session, kind, payload, driver=None, raw_key=None):
    event = CoachEvent.objects.create(session=session, driver=driver, kind=kind, payload=payload, raw_key=raw_key)
    if connection.vendor == "postgresql":
        # PostgreSQL delivers NOTIFY on commit. CoachEvent remains the durable outbox.
        with connection.cursor() as cursor:
            cursor.execute("SELECT pg_notify('livecoach', %s)", [str(session.pk)])
    return event


@transaction.atomic
def ingest(track_id, recording_id, packet, recovery=False):
    track = TimingTrack.objects.select_for_update().get(pk=track_id)
    key = f"{recording_id}:{packet['seq']}"
    if TimingPacket.objects.filter(key=key).exists():
        return 0
    received = datetime.fromisoformat(packet["receivedAt"].replace("Z", "+00:00"))
    TimingPacket.objects.create(key=key, track=track, received_at=received)
    now = timezone.now()
    track.worker_at = None if recovery else now
    if packet["type"] == "connection":
        track.connection = packet.get("state", "unknown")
        if track.connection != "connected":
            track.error = "Bronverbinding onderbroken; passages kunnen ontbreken."
    elif packet["type"] == "packet":
        track.packet_at = now
        adapter = ApexAdapter(track.parser_state)
        passages = adapter.apply(packet)
        track.parser_state = adapter.state
        track.title = adapter.state["title"]
        track.entrants = adapter.entrants()
        track.capabilities = {"laps": adapter.supported, "sectors": False,
                              "validity": "unknown", "profile": "APEX llp/tlp or observed race passages" if adapter.supported else "unknown"}
        track.capabilities["sectors"] = bool(adapter.sector_ids())
        track.capabilities["sectorIds"] = adapter.sector_ids()
        if packet.get("payload", "").strip():
            track.timing_at = now
        track.error = "" if adapter.supported else "Wachten op een ondersteunde timingtabel."
        count = 0
        standings = {row["identity"]: row for row in adapter.standings()}
        for session in FollowSession.objects.select_for_update().filter(track=track, state="active"):
            if received < session.started_at:
                continue
            for driver in FollowDriver.objects.select_for_update().filter(session=session):
                row = standings.get(driver.identity)
                if row is None:
                    # Upgrade a legacy selection made before a kart swap. Verify its
                    # complete old hash: matching a name alone could merge different races.
                    for candidate in standings.values():
                        source_row = adapter.state["rows"][candidate["row"]]
                        legacy = "\0".join([adapter.state["generation"], source_row["run"], candidate["row"], candidate["name"], driver.kart])
                        if hashlib.sha256(legacy.encode()).hexdigest() == driver.identity:
                            driver.identity = candidate["identity"]
                            driver.save(update_fields=["identity"])
                            row = candidate
                            break
                if row and driver.kart != row["kart"]:
                    old_kart = driver.kart
                    driver.kart = row["kart"][:30]
                    driver.save(update_fields=["kart"])
                    publish(session, "kart", {"name": driver.name, "oldKart": old_kart, "newKart": driver.kart, "referenceBest": dict(driver.best), "message": f"Kartwissel #{old_kart} → #{driver.kart}; besttijden behouden."}, driver=driver)
                for passage in passages:
                    if passage["identity"] != driver.identity:
                        continue
                    passage_key = hashlib.sha256(f"{session.pk}:{driver.identity}:{driver.block}:{passage['metric']}:{passage['lap']}".encode()).hexdigest()
                    if CoachEvent.objects.filter(raw_key=passage_key).exists():
                        continue
                    if passage.get("pitLap"):
                        feedback = {"metric": "lap", "timeMs": passage["timeMs"], "deltaMs": None, "referenceMs": driver.best.get("lap"), "deltaText": None, "message": "Pitronde · referentie behouden", "pitLap": True}
                    else:
                        driver.best, feedback = delta_feedback(driver.best, passage["metric"], passage["timeMs"])
                    feedback.update({"driverId": driver.pk, "name": driver.name, "kart": driver.kart,
                                     "lap": passage["lap"], "block": driver.block,
                                     "lapCountKnown": passage["lapCountKnown"],
                                     "receivedAt": packet["receivedAt"], "publishedAt": now.isoformat(),
                                     "rawKey": key, "gap": passage["gap"], "validity": passage["validity"]})
                    metrics = dict(driver.last.get("byMetric", {}))
                    metrics[passage["metric"]] = dict(feedback)
                    driver.last = {**feedback, "byMetric": metrics}
                    driver.save(update_fields=["best", "last"])
                    publish(session, "feedback", feedback, driver=driver, raw_key=passage_key)
                    count += 1
                row = standings.get(driver.identity)
                if row and row["finished"]:
                    finish_key = hashlib.sha256(f"driver-finish:{session.pk}:{driver.identity}:{driver.block}".encode()).hexdigest()
                    if not CoachEvent.objects.filter(raw_key=finish_key).exists():
                        publish(session, "finish", {"message": "Finish bevestigd door APEX", "name": driver.name,
                            "driverId": driver.pk, "receivedAt": packet["receivedAt"]}, driver=driver, raw_key=finish_key)
            if adapter.state.get("flag") == "lf":
                finish_key = hashlib.sha256(f"session-finish:{session.pk}:{adapter.state['generation']}:{adapter.state.get('finishedAt')}".encode()).hexdigest()
                if not CoachEvent.objects.filter(raw_key=finish_key).exists():
                    publish(session, "finish", {"message": "🏁 Finishvlag · baansessie gefinisht. Laatste passages blijven binnenkomen.",
                        "receivedAt": packet["receivedAt"]}, raw_key=finish_key)
        track.save()
        if connection.vendor == "postgresql" and packet.get("payload", "").strip():
            with connection.cursor() as cursor:
                cursor.execute("SELECT pg_notify('livecoach', %s)", [f"track:{track.pk}"])
        return count
    track.save()
    return 0


def display_clock(track, now):
    state = track.parser_state or {}
    race = ApexAdapter(state).race_progress() if state else {}
    source_now = int(now.timestamp() * 1000)
    rate = 1 if track.connection == "connected" and track.worker_at and (now - track.worker_at).total_seconds() < 45 else 0
    if track.mode == "replay":
        from .live_models import TimingSimulation
        from .live_simulation import target_position
        sim = TimingSimulation.objects.filter(track=track).select_related("recording").first()
        rate = sim.speed if sim and sim.state == "playing" else 0
        if sim:
            segment = sim.recording.segments[sim.segment]
            origin = segment.get("state", {}).get("clockMs")
            source_now = origin + target_position(sim, now) if origin is not None else state.get("clockMs", 0)
        else:
            source_now = state.get("clockMs", 0)
    elif not rate:
        source_now = state.get("clockMs", source_now)
    deadline = state.get("race_deadline_ms")
    if deadline is not None and not race.get("finished"):
        race["remainingMs"] = max(0, deadline - source_now)
    return {**race, "rate": rate, "asOf": now.isoformat()}


def track_data(track):
    now = timezone.now()
    fresh = bool(track.worker_at and (now - track.worker_at).total_seconds() < 45)
    return {"id": track.pk, "slug": track.slug, "name": track.name, "mode": track.mode,
            "title": track.title, "connection": track.connection if fresh else "offline",
            "workerActive": fresh, "packetAt": track.packet_at.isoformat() if track.packet_at else None,
            "timingAt": track.timing_at.isoformat() if track.timing_at else None,
            "error": track.error, "capabilities": track.capabilities,
            "finished": track.parser_state.get("flag") == "lf",
            "finishedAt": track.parser_state.get("finishedAt"),
            "flag": track.parser_state.get("flag", ""),
            "sessionBests": ApexAdapter(track.parser_state).session_bests() if track.parser_state else {},
            "sessionRecords": ApexAdapter(track.parser_state).session_records() if track.parser_state else {},
            "race": display_clock(track, now),
            "comments": track.parser_state.get("comments", []),
            "standings": ApexAdapter(track.parser_state).standings() if track.parser_state else [],
            "entrants": track.entrants if fresh else []}


def timing_color(value, bests):
    result = present_feedback(value)
    duration, metric = result.get("timeMs"), result.get("metric")
    fastest = bool(duration and bests.get(metric) and duration <= bests[metric] and not result.get("pitLap"))
    delta = result.get("deltaMs")
    result["color"] = "purple" if fastest else "green" if delta is not None and delta <= 0 else "orange" if delta is not None and delta > 0 else "neutral"
    result["isSessionBest"] = fastest
    if value.get("byMetric"):
        result["byMetric"] = {key: timing_color(passage, bests) for key, passage in value["byMetric"].items()}
    return result


def snapshot(session):
    current = {e["identity"] for e in session.track.entrants}
    finished = {row["identity"] for row in ApexAdapter(session.track.parser_state).standings() if row["finished"]} if session.track.parser_state else set()
    events = list(session.events.order_by("-pk")[:50])
    rows = ApexAdapter(session.track.parser_state).standings() if session.track.parser_state else []
    adapter = ApexAdapter(session.track.parser_state) if session.track.parser_state else None
    race = adapter.race_progress() if adapter else {}
    session_bests = adapter.session_bests() if adapter else {}
    row_by_identity = {row["identity"]: row for row in rows}
    pit_settings = session.pit_settings or settings_for(session.track)
    drivers = list(session.drivers.order_by("-primary", "pk"))
    identities = {driver.identity for driver in drivers if driver.pit_enabled}
    positions = {row["identity"]: row["position"] for row in rows}
    kart_history = {driver.pk: [] for driver in drivers}
    kart_events = session.events.filter(kind="kart", driver_id__in=kart_history)
    if session.track.mode == "replay":
        restart = session.events.filter(kind="reset", payload__message__startswith="Simulatie herstart").order_by("-pk").first()
        if restart:
            kart_events = kart_events.filter(pk__gt=restart.pk)
    for event in kart_events.order_by("pk"):
        old_kart = event.payload.get("oldKart")
        if old_kart is None:
            # Earlier timing workers stored the same transition as a message.
            match = re.match(r"Kartwissel #(.*?) → #", event.payload.get("message", ""))
            old_kart = match.group(1) if match else None
        if old_kart:
            kart_history[event.driver_id].append({"kart": old_kart, "best": event.payload.get("referenceBest", {})})
    pits = {row["identity"]: forecast(rows, {**row, "finished": row["finished"] or session.track.parser_state.get("flag") == "lf"}, pit_settings, race) for row in rows if session.state == "active" and row["identity"] in identities}
    result = {"pitSettings": pit_settings, "id": str(session.pk), "name": session.name, "state": session.state,
            "startedAt": session.started_at.isoformat(), "track": track_data(session.track),
            "drivers": [{"id": d.pk, "identity": d.identity, "name": d.name, "kart": d.kart,
                         "bestColors": {metric: timing_color({"metric": metric, "timeMs": value}, session_bests)["color"] for metric, value in d.best.items()},
                         "primary": d.primary, "position": positions.get(d.identity), "kartHistory": kart_history[d.pk], "pitEnabled": d.pit_enabled, "block": d.block, "best": d.best, "last": timing_color(d.last, session_bests),
                         "lastPitMs": row_by_identity.get(d.identity, {}).get("lastPitMs"),
                         "finished": d.identity in finished, "pit": pits.get(d.identity),
                         "present": d.identity in current} for d in drivers],
            "cursor": events[0].pk if events else 0,
            "events": [{"id": e.pk, "kind": e.kind, "payload": present_feedback(e.payload) if e.kind == "feedback" else e.payload} for e in reversed(events)]}
    if session.track.mode == "replay":
        from .live_models import TimingSimulation
        from .live_simulation import simulation_data
        simulation = TimingSimulation.objects.filter(track=session.track).select_related("recording").first()
        if simulation:
            result["simulation"] = simulation_data(simulation)
    return result
