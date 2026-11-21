"""Training comparisons and immutable, owner-scoped kart assessment templates."""
from statistics import median

SCORE_TEMPLATE = {"version": 1, "scale": {"min": 1, "max": 5}, "elements": [
    {"id": "acceleration", "label": "Acceleratie"}, {"id": "topSpeed", "label": "Topsnelheid"},
    {"id": "braking", "label": "Remmen"}, {"id": "frontGrip", "label": "Voorgrip"},
    {"id": "rearGrip", "label": "Achtergrip"}, {"id": "balance", "label": "Balans"}]}


def best_times(row):
    values = {**row.get("sectorBests", {}), "lap": row.get("bestLapMs")}
    # Source sector snapshots can be incomplete; only persisted clean sector records qualify.
    return {metric: value for metric, value in values.items() if type(value) is int and value > 0}


def training_comparison(driver, rows, session_bests, parser_state=None):
    parser_state = parser_state or {}
    own = next((row for row in rows if row["identity"] == driver.identity), None)
    own_best = best_times(own) if own else {}
    for metric, value in driver.best.items():
        if value:
            own_best[metric] = min(own_best.get(metric, value), value)
    ranked = []
    for row in rows if own else []:
        raw = parser_state.get("rows", {}).get(row.get("row"), {})
        best = best_times(row)
        observed = raw.get("observed_best_lap")
        if observed:
            best["lap"] = min(best.get("lap", observed), observed)
        if row["identity"] == driver.identity:
            best.update(own_best)
        if best.get("lap"):
            ranked.append({"identity": row["identity"], "name": row["name"], "kart": row["kart"],
                           "best": best, "selected": row["identity"] == driver.identity,
                           "latest": latest_times(row, raw, driver if row["identity"] == driver.identity else None, session_bests)})
    ranked.sort(key=lambda item: (item["best"]["lap"], item["name"], item["identity"]))
    for index, item in enumerate(ranked):
        item["position"] = index + 1
    index = next((i for i, item in enumerate(ranked) if item["selected"]), None)
    if index is None:
        chosen = ([ranked[0]] if ranked else []) + ([{"identity": driver.identity, "name": driver.name, "kart": driver.kart, "selected": True, "position": None, "best": own_best, "latest": latest_times(own, parser_state.get("rows", {}).get(own.get("row"), {}), driver, session_bests)}] if own else [])
    elif index < 2:
        chosen = ranked[:3]
    else:
        chosen = [ranked[i] for i in dict.fromkeys([0, index - 1, index, index + 1]) if i < len(ranked)]
    # Preserve the previous API fields for existing clients while the UI uses driver rows.
    comparisons = []
    for role, i in (("faster", index - 1 if index is not None and index else None),
                    ("slower", index + 1 if index is not None and index + 1 < len(ranked) else None)):
        item = ranked[i] if i is not None else None
        values = item["best"] if item else {}
        comparisons.append({"role": role, "name": item["name"] if item else None, "kart": item["kart"] if item else None,
            "best": values, "deltas": {metric: own_best[metric] - value for metric, value in values.items() if metric in own_best}})
    session_bests = session_bests if own else {}
    comparisons.append({"role": "fastest", "name": None, "best": session_bests,
        "deltas": {metric: own_best[metric] - value for metric, value in session_bests.items() if metric in own_best}})
    sectors = [f"S{i}" for i in (1, 2, 3) if f"s{i}" in parser_state.get("headers", {}).values()]
    ideal = {metric: session_bests.get(metric) for metric in sectors}
    ideal["lap"] = sum(ideal.values()) if sectors and all(type(value) is int and value > 0 for value in ideal.values()) else None
    recent = [item["timeMs"] for item in (own or {}).get("recentLaps", []) if item.get("kart") == driver.kart and item.get("timeMs")][-3:]
    potential = {metric: max(0, own_best[metric] - reference)
                 if metric in own_best and reference is not None else None
                 for metric, reference in ideal.items()}
    return {"position": index + 1 if index is not None else None, "potentialMs": potential,
            "ownBest": own_best, "comparisons": comparisons, "rows": chosen, "ideal": ideal,
            "ownLatest": latest_times(own, parser_state.get("rows", {}).get((own or {}).get("row"), {}), driver, session_bests) if own else {},
            "paceMs": int(median(recent)) if recent else None, "paceLaps": len(recent), "present": own is not None}


def latest_times(row, raw, driver=None, session_bests=None):
    """Cycle labels use observed passages, never an invented physical track position."""
    values = {**row.get("sectors", {}), "lap": row.get("lastLapMs")}
    laps = dict(raw.get("sector_seen", {}))
    if raw.get("observed"):
        laps["lap"] = raw["observed"]
    if row.get("laps") is not None and raw.get("observed", 0) != row["laps"]:
        laps = {}  # A reconnect snapshot may be ahead of the last observed crossing.
    feedback = getattr(driver, "last", {}) if driver else {}
    for metric, passage in feedback.get("byMetric", {}).items():
        if passage.get("timeMs") and passage.get("lap") is not None:
            values[metric], laps[metric] = passage["timeMs"], passage["lap"]
    if feedback.get("metric") and feedback.get("timeMs") and feedback.get("lap") is not None:
        values[feedback["metric"]], laps[feedback["metric"]] = feedback["timeMs"], feedback["lap"]
    cycle = max(laps.values()) if laps else None
    official = row.get("laps") is not None
    known = dict(raw.get("training_times", {}))
    known.update(feedback.get("byMetric", {}))
    if feedback.get("metric"):
        known[feedback["metric"]] = feedback
    bests = best_times(row)
    if raw.get("observed_best_lap"):
        bests["lap"] = min(bests.get("lap", raw["observed_best_lap"]), raw["observed_best_lap"])
    for metric, value in (getattr(driver, "best", {}) if driver else {}).items():
        if value:
            bests[metric] = min(bests.get(metric, value), value)
    result = {}
    for metric, value in values.items():
        passage = known.get(metric, {})
        matches = passage.get("timeMs") == value and value is not None
        difference = passage.get("deltaMs") if matches else value - bests[metric] if value is not None and metric in bests else None
        pit = passage.get("pitLap", False) if matches else False
        global_best = (session_bests or {}).get(metric)
        personal_best = value is not None and metric in bests and value <= bests[metric] and not pit
        shade = "purple" if value and global_best and value <= global_best and not pit else "green" if personal_best or difference is not None and difference <= 0 else "orange" if difference is not None else "neutral"
        result[metric] = {"timeMs": value, "lap": laps.get(metric), "lapCountKnown": official,
            "phase": "unknown" if value is None or metric not in laps else "current" if laps[metric] == cycle else "previous",
            "active": matches and metric in laps and laps[metric] == cycle, "deltaMs": difference, "color": shade}
    return result


def used_karts(session, driver):
    result = {driver.kart} if driver.kart else set()
    events = session.events.filter(driver=driver, kind="kart")
    if session.track.mode == "replay":
        rewind = session.events.filter(kind="reset", payload__rewind=True).order_by("-pk").first()
        if rewind:
            events = events.filter(pk__gt=rewind.pk)
    for event in events:
        for key in ("oldKart", "newKart"):
            if event.payload.get(key):
                result.add(str(event.payload[key]))
    return sorted(result)


def kart_timing(session, driver, kart):
    result = {}
    for event in session.events.filter(driver=driver, kind="feedback"):
        value = event.payload
        metric, duration = value.get("metric"), value.get("timeMs")
        if str(value.get("kart")) == kart and not value.get("pitLap") and metric in {"lap", "S1", "S2", "S3"} and type(duration) is int and duration > 0:
            result[metric] = min(result.get(metric, duration), duration)
    return result


def report_data(report):
    return {"id": str(report.pk), "trackId": report.track_id, "track": report.track.name,
        "pilot": report.pilot, "kart": report.kart, "createdAt": report.created_at.isoformat(),
        "sessionName": report.session_name, "conditions": report.conditions, "scores": report.scores,
        "notes": report.notes, "timing": report.timing, "template": report.template}
