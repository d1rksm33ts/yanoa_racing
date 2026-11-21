"""Project existing Live Coach timing to a device; never opens an Apex stream."""
from django.utils import timezone
from .live_core import ApexAdapter
from .live_service import display_clock, timing_color
from .live_training import training_comparison
from .live_pit import forecast, settings_for, pace
from .telemetry_pit import pit_display, exit_position


def timing_for(device, now=None):
    now = now or timezone.now()
    base = {"schema_version": 1, "assignment_revision": device.assignment_revision,
            "valid": False, "status": "unassigned", "source": None,
            "session_id": None, "driver_name": None, "kart_number": None,
            "position": None, "lap_count": None, "last_lap_ms": None, "best_lap_ms": None,
            "race_remaining_ms": None, "activity": None, "metrics": [], "training": None, "pit": None,
            "latest_sector": None, "gap_ahead_ms": None, "race_rate": 0, "finished": False}
    driver = device.assigned_driver
    if driver is None:
        return base
    session, track = driver.session, driver.session.track
    base.update(session_id=str(session.pk), driver_name=driver.name[:32], kart_number=driver.kart[:12],
                source="replay" if track.mode == "replay" else "apex", activity=session.activity)
    if session.owner_id != device.owner_id or session.state != "active":
        return {**base, "status": "session_stopped"}
    from .live_models import TimingSimulation
    simulation = TimingSimulation.objects.filter(track=track).first() if track.mode == "replay" else None
    if simulation is not None and simulation.state == "rewinding":
        return {**base, "status": "replay_rewinding"}
    ended = (simulation is not None and simulation.state == "finished") or (track.mode != "replay" and track.parser_state.get("flag") == "lf")
    if not ended and (not track.worker_at or (now - track.worker_at).total_seconds() > 45 or track.connection != "connected"):
        return {**base, "status": "source_offline"}
    adapter = ApexAdapter(track.parser_state)
    rows = adapter.standings()
    row = next((r for r in rows if r["identity"] == driver.identity), None)
    if row is None:
        return {**base, "status": "driver_missing"}
    status = "finished" if ended else "live"
    if track.mode == "replay":
        if simulation is None or simulation.state in {"error", "stopped"}:
            return {**base, "status": "source_offline"}
        status = "replay_" + simulation.state
    race = display_clock(track, now)
    metrics = []
    bests = adapter.session_bests()
    comparison = training_comparison(driver, rows, bests, track.parser_state)
    training = comparison if session.activity == "training" else None
    last = timing_color(driver.last, bests)
    for metric in [*adapter.sector_ids(), "lap"]:
        passage = (training["ownLatest"].get(metric, {}) if training else
                   last.get("byMetric", {}).get(metric, last if last.get("metric") == metric else {}))
        value = passage.get("timeMs")
        if value is None:
            value = row.get("lastLapMs") if metric == "lap" else row.get("sectors", {}).get(metric)
        ideal = training["ideal"].get(metric) if training else None
        metrics.append({"id": metric, "time_ms": value, "delta_ms": passage.get("deltaMs"),
            "best_ms": training["ownBest"].get(metric) if training else driver.best.get(metric, row.get("bestLapMs") if metric == "lap" else row.get("sectorBests", {}).get(metric)),
            "color": passage.get("color", "neutral"), "active": passage.get("active", last.get("metric") == metric),
            "potential_ms": comparison["potentialMs"].get(metric),
            "ideal_delta_ms": training["potentialMs"].get(metric) if training else None})
    # A completed lap must retain its last sector. A new S1 then wins by cycle number.
    seen = track.parser_state.get("rows", {}).get(row["row"], {}).get("sector_seen", {})
    sector_order = adapter.sector_ids()
    observed = [(seen[m], i, m) for i, m in enumerate(sector_order) if type(seen.get(m)) is int]
    latest_sector = max(observed)[2] if observed else None
    ahead = next((r for r in rows if row.get("position") and r.get("position") == row["position"] - 1), None)
    gap = None
    if (ahead and type(row.get("gapMs")) is int and type(ahead.get("gapMs")) is int
            and not row.get("gapEstimated") and not ahead.get("gapEstimated")
            and (row.get("laps") is None or ahead.get("laps") is None or row["laps"] == ahead["laps"])):
        difference = row["gapMs"] - ahead["gapMs"]
        if difference >= 0:
            gap = difference
    pit = None
    if session.activity == "endurance":
        projected = forecast(rows, {**row, "finished": row["finished"] or race.get("finished", False)},
                             session.pit_settings or settings_for(track), race) if driver.pit_enabled else {}
        pit = {"enabled": driver.pit_enabled, "in_pit": row.get("inPit", False), "stops_done": row.get("pitCount"),
               "stops_left": projected.get("remainingStops"), "remaining_ms": projected.get("pitRemainingMs"),
               "pace_ms": projected.get("paceMs", pace(row)), "status": projected.get("status", "disabled"),
               "after_stops": projected.get("correctedPosition"), "at_finish": projected.get("endPosition"),
               "advice": projected.get("coaching", {}).get("text", "")[:48]}
    facts = pit_display(row, track.parser_state.get("rows", {}).get(row["row"], {}), track, session, now, race, simulation)
    pit = {**(pit or {}), **facts}
    pit["exit_position"] = exit_position(row, track.parser_state.get("rows", {}).get(row["row"], {}), rows, session.pit_settings or {}, facts["elapsed_ms"]) if facts["phase"] == "in" else None
    lap_metric = metrics[-1]
    return {**base, "valid": True, "status": status, "kart_number": row["kart"][:12],
            "position": row.get("position"), "lap_count": row.get("laps"),
            "last_lap_ms": lap_metric["time_ms"], "best_lap_ms": lap_metric["best_ms"],
            "race_remaining_ms": race.get("remainingMs"), "race_rate": race.get("rate", 0),
            "metrics": metrics, "latest_sector": latest_sector, "gap_ahead_ms": gap, "finished": ended or row["finished"] or race.get("finished", False),
            "training": {"position": training["position"], "pace_ms": training["paceMs"], "pace_laps": training["paceLaps"], "ideal_lap_ms": training["ideal"]["lap"]} if training else None,
            "pit": pit}
