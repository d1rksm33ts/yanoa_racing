"""Pure, serializable APEX lap adapter and timing arithmetic. No browser or database."""
import hashlib
import re
import uuid
from html.parser import HTMLParser
from datetime import datetime
from statistics import median


class Text(HTMLParser):
    def __init__(self, value):
        super().__init__(convert_charrefs=True)
        self.parts = []
        self.feed(value)

    def handle_data(self, data):
        self.parts.append(data)


def text(value):
    return " ".join("".join(Text(value).parts).split())


def milliseconds(value):
    match = re.fullmatch(r"(?:(\d+):)?(\d{1,3})[.,](\d{3})", value.strip())
    if not match:
        return None
    minutes, seconds, fraction = match.groups()
    if minutes and int(seconds) >= 60:
        return None
    result = (int(minutes or 0) * 60 + int(seconds)) * 1000 + int(fraction)
    return result if result > 0 else None


def delta_feedback(best, metric, duration_ms):
    if metric not in {"lap", "S1", "S2", "S3"} or type(duration_ms) is not int or duration_ms <= 0:
        raise ValueError("Invalid passage")
    reference = best.get(metric)
    delta = duration_ms - reference if reference is not None else None
    tenths = None if delta is None else ((abs(delta) + 50) // 100) * (-1 if delta < 0 else 1)
    label = "Ronde" if metric == "lap" else metric
    spoken = "referentie gezet" if delta is None else delta_text(delta)
    updated = dict(best)
    updated[metric] = min(reference, duration_ms) if reference is not None else duration_ms
    return updated, {"metric": metric, "timeMs": duration_ms, "referenceMs": reference,
                     "deltaMs": delta, "tenths": tenths, "deltaText": None if delta is None else spoken,
                     "message": f"{label} {spoken}"}


def delta_text(delta):
    return f"{'-' if delta < 0 else '+'}{abs(delta) // 1000}.{abs(delta) % 1000:03d}s"


def present_feedback(value):
    result = dict(value)
    if type(result.get("deltaMs")) is int:
        result["deltaText"] = delta_text(result["deltaMs"])
        label = "Ronde" if result.get("metric") == "lap" else result.get("metric", "")
        result["message"] = f"{label} {result['deltaText']}"
    return result


class Comments(HTMLParser):
    """Read the official APEX com snapshot as plain text, never executable HTML."""
    def __init__(self, value):
        super().__init__(convert_charrefs=True)
        self.rows, self.row, self.capture = [], None, None
        self.feed(value)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "p":
            self.row = {"time": "", "kart": "", "kind": "msg", "message": ""}
        elif self.row is not None:
            if tag == "b":
                self.capture = "time"
            elif tag == "span":
                if attrs.get("data-flag"):
                    self.row["kind"] = attrs["data-flag"]
                if "com_no" in attrs.get("class", "").split():
                    self.capture = "kart"

    def handle_data(self, value):
        if self.row is not None:
            self.row[self.capture or "message"] += value

    def handle_endtag(self, tag):
        if tag in {"b", "span"}:
            self.capture = None
        elif tag == "p" and self.row is not None:
            self.row = {key: " ".join(value.split()) for key, value in self.row.items()}
            if self.row["message"]:
                self.rows.append(self.row)
            self.row = None


class Grid(HTMLParser):
    def __init__(self, html):
        super().__init__(convert_charrefs=True)
        self.rows = []
        self.row = None
        self.cell = None
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "tr":
            self.row = {"id": attrs.get("data-id", ""), "head": "head" in attrs.get("class", "").split(),
                        "position": int(attrs["data-pos"]) if attrs.get("data-pos", "").isdigit() else None, "cells": []}
        elif tag == "td" and self.row is not None:
            self.cell = {"id": attrs.get("data-id", ""), "type": attrs.get("data-type", ""), "class": attrs.get("class", ""), "text": ""}
        elif self.cell is not None and attrs.get("data-id"):
            self.cell["id"] = attrs["data-id"]

    def handle_data(self, value):
        if self.cell is not None:
            self.cell["text"] += value

    def handle_endtag(self, tag):
        if tag == "td" and self.cell is not None and self.row is not None:
            self.cell["text"] = " ".join(self.cell["text"].split())
            self.row["cells"].append(self.cell)
            self.cell = None
        elif tag == "tr" and self.row is not None:
            self.rows.append(self.row)
            self.row = None


class ApexAdapter:
    def __init__(self, state=None):
        self.state = state or {"title": "", "generation": uuid.uuid4().hex, "headers": {}, "rows": {}}

    def field(self, row, kind):
        column = next((c for c, k in self.state["headers"].items() if k == kind), None)
        return row["cells"].get(column, "") if column else ""

    def entrant(self, rid, row):
        name, kart = self.field(row, "dr"), self.field(row, "no")
        scope = [self.state["generation"], row["run"], rid, name]
        # Seed with the legacy key once: existing selections survive this upgrade.
        # Subsequent kart changes belong to the same driver, not a new identity.
        if row.get("identity_scope") != scope:
            if row.get("identity_scope") and row["identity_scope"][3] != name:
                for field in ("recent_laps", "pit_samples", "in_pit", "pit_enter_ms", "pit_dirty", "pit_sample_pending", "completed_pits", "last_pit_ms", "last_pit_exit_ms", "pit_exit_pending", "pit_entry_field", "sector_bests", "observed_best_lap", "lap_crossings", "training_times", "training_latest_metric"):
                    row.pop(field, None)
            row["driver_identity"] = hashlib.sha256("\0".join(scope + [kart]).encode()).hexdigest()
            row["identity_scope"] = scope
        return {"identity": row["driver_identity"], "name": name, "kart": kart, "row": rid}

    @property
    def supported(self):
        kinds = set(self.state["headers"].values())
        return {"dr", "no", "llp"}.issubset(kinds) and ("tlp" in kinds or {"gap", "blp"}.issubset(kinds))

    def entrants(self):
        return [self.entrant(rid, row) for rid, row in self.state["rows"].items() if self.field(row, "dr")]

    def sector_ids(self):
        return [f"S{i}" for i in (1, 2, 3) if f"s{i}" in self.state["headers"].values()]

    def standings(self):
        result = []
        for rid, row in self.state["rows"].items():
            if not self.field(row, "dr"):
                continue
            rank = self.field(row, "rk")
            laps = self.field(row, "tlp")
            result.append({**self.entrant(rid, row),
                "position": row.get("position") or (int(rank) if rank.isdigit() else None),
                "lastLapMs": milliseconds(self.field(row, "llp")),
                "bestLapMs": milliseconds(self.field(row, "blp")),
                "laps": int(laps) if laps.isdigit() else None,
                "sectors": {f"S{i}": milliseconds(self.field(row, f"s{i}")) for i in (1, 2, 3)},
                "finished": self.driver_finished(row),
                "gap": self.field(row, "gap"), "inPit": row.get("in_pit", False),
                "pitCount": max(row.get("completed_pits", 0), max(0, int(self.field(row, "pit") or "0") - int(row.get("in_pit", False)))) if (self.field(row, "pit") or "0").isdigit() else row.get("completed_pits", 0),
                "pitElapsedMs": max(0, self.state.get("clockMs", 0) - row.get("pit_enter_ms", self.state.get("clockMs", 0))) if row.get("in_pit") else None,
                "lastPitMs": row.get("last_pit_ms"), "lastPitExitMs": row.get("last_pit_exit_ms"),
                "sectorBests": row.get("sector_bests", {}),
                "pitUnreflected": bool(row.get("pit_sample_pending")) and not row.get("in_pit", False),
                "pitSamples": row.get("pit_samples", []), "recentLaps": row.get("recent_laps", []),
                "observedPassages": row.get("observed", 0)})
        result = sorted(result, key=lambda row: (row["position"] or 99999, row["name"].casefold()))
        leader = next((row for row in result if row["position"] == 1), None)
        lapped_group = False
        for row in result:
            if re.search(r"(?:Ronde|Lap|Tour)", row["gap"], re.I) and row["position"] != 1:
                lapped_group = True
            row["gapEstimated"] = False
            row["gapMs"] = 0 if row["position"] == 1 else milliseconds(row["gap"])
            if row["position"] != 1 and (lapped_group or leader and row["laps"] is not None and leader["laps"] is not None and row["laps"] < leader["laps"]):
                row["gapMs"] = None
                if leader and row["laps"] is not None:
                    lap = str(row["laps"])
                    own_cross = self.state["rows"][row["row"]].get("lap_crossings", {}).get(lap)
                    lead_cross = self.state["rows"][leader["row"]].get("lap_crossings", {}).get(lap)
                    if own_cross is not None and lead_cross is not None:
                        row["gapMs"] = max(0, own_cross - lead_cross)
                        row["gapEstimated"] = True
            elif row["gap"].strip() in {"0.000", "0,000", "0:00.000"}:
                row["gapMs"] = 0
        return result

    def session_bests(self):
        best = dict(self.state.get("session_best_times", {}))
        for row in self.standings():
            lap_values = [v for v in [row.get("bestLapMs"), self.state["rows"][row["row"]].get("observed_best_lap")] if v]
            raw = self.state["rows"][row["row"]]
            sectors = dict(row.get("sectorBests", {}))
            if not raw.get("in_pit") and not raw.get("pit_dirty"):
                for metric, value in row["sectors"].items():
                    if value:
                        sectors[metric] = min(sectors.get(metric, value), value)
            for metric, value in {"lap": min(lap_values) if lap_values else None, **sectors}.items():
                if value and (metric not in best or value < best[metric]):
                    best[metric] = value
        return best

    def session_records(self):
        bests = self.session_bests()
        records = {metric: {"timeMs": value, "drivers": []} for metric, value in bests.items()}
        for metric, old in self.state.get("session_records", {}).items():
            if metric in records and old.get("timeMs") == bests[metric]:
                records[metric]["drivers"] = list(old.get("drivers", []))
        for row in self.standings():
            raw = self.state["rows"][row["row"]]
            lap = [value for value in (row.get("bestLapMs"), raw.get("observed_best_lap")) if value]
            values = {"lap": min(lap) if lap else None, **row.get("sectorBests", {})}
            if not raw.get("in_pit") and not raw.get("pit_dirty"):
                for metric, value in row["sectors"].items():
                    if value:
                        values[metric] = min(values.get(metric, value), value)
            for metric, value in values.items():
                if metric not in records or value != bests[metric]:
                    continue
                holders = records[metric]["drivers"]
                holder = {"identity": row["identity"], "name": row["name"]}
                if not any(item["identity"] == holder["identity"] for item in holders):
                    holders.append(holder)
        return records

    def race_progress(self):
        if self.state.get("flag") == "lf":
            return {"remainingMs": 0, "remainingLaps": 0, "finished": True}
        deadline = self.state.get("race_deadline_ms")
        return {"remainingMs": max(0, deadline - self.state.get("clockMs", deadline)) if deadline is not None else None,
                "remainingLaps": self.state.get("race_remaining_laps"),
                "currentLap": self.state.get("race_current_lap"), "totalLaps": self.state.get("race_total_laps"), "finished": False}

    def driver_finished(self, row):
        col = next((c for c, kind in self.state["headers"].items() if kind == "sta"), None)
        return "sf" in row.get("classes", {}).get(col, "").split()

    def apply(self, packet):
        if packet.get("type") != "packet" or packet.get("encoding") != "utf8":
            return []
        stamp = packet.get("originalReceivedAt", packet["receivedAt"])
        clock_ms = int(datetime.fromisoformat(stamp.replace("Z", "+00:00")).timestamp() * 1000)
        # Evaluate after the complete packet: APEX may send lap count before lap time.
        previous_rows = self.state["rows"].copy()
        prior = {rid: self.field(row, "tlp") or "0" for rid, row in previous_rows.items()}
        baseline = prior.copy()
        training_references = {}
        for rid, row in previous_rows.items():
            values = dict(row.get("sector_bests", {}))
            laps = [value for value in (milliseconds(self.field(row, "blp")), row.get("observed_best_lap")) if value]
            if laps:
                values["lap"] = min(laps)
            training_references[rid] = values
        identities = {rid: self.entrant(rid, row)["identity"] for rid, row in previous_rows.items()}
        updated, snapshots, markers, pits = set(), set(), set(), set()
        sector_updates = []
        for line in packet.get("payload", "").splitlines():
            fields = line.split("|", 2)
            if len(fields) != 3:
                continue
            target, action, value = fields
            if target == "init":
                # Reconnect init is a snapshot, not a new race or new passage.
                prior = {}
                self.state["rows"] = {}
                self.state["headers"] = {}
            elif target == "title2":
                title = text(value)
                if title != self.state["title"]:
                    self.state = {"title": title, "generation": uuid.uuid4().hex, "headers": {}, "rows": {}}
                    prior, baseline, previous_rows, identities = {}, {}, {}, {}
            elif target == "dyn1":
                if action == "countdown" and value.isdigit():
                    self.state["race_deadline_ms"] = clock_ms + int(value)
                    self.state.pop("race_remaining_laps", None)
                    self.state.pop("race_current_lap", None)
                    self.state.pop("race_total_laps", None)
                elif action == "text":
                    count = re.fullmatch(r"(?:Rondes?|Laps?|Tours?|Vueltas?|Giros?)\s+(\d+)\s*/\s*(\d+)", text(value), re.I)
                    if count and int(count[2]) > 0 and int(count[1]) <= int(count[2]):
                        self.state["race_current_lap"] = int(count[1])
                        self.state["race_total_laps"] = int(count[2])
                        self.state["race_remaining_laps"] = max(0, int(count[2]) - int(count[1]))
                        self.state.pop("race_deadline_ms", None)
            elif target == "light":
                previous_flag = self.state.get("flag")
                self.state["flag"] = action
                if action == "lf" and previous_flag != "lf":
                    self.state["finishedAt"] = packet["receivedAt"]
                elif action == "lg":
                    self.state.pop("finishedAt", None)
            elif target == "com":
                self.state["comments"] = Comments(value).rows[:200]
            elif target == "grid":
                for row in Grid(value).rows:
                    if row["head"]:
                        self.state["headers"] = {re.sub(r"^.*c", "c", c["id"]): (c["type"] or {"rondes": "tlp", "laps": "tlp", "tours": "tlp", "totale pit tijd": "pit_total"}.get(c["text"].casefold(), "")) for c in row["cells"]}
                        continue
                    rid = row["id"]
                    if not re.fullmatch(r"r\d+", rid):
                        continue
                    old = self.state["rows"].get(rid, previous_rows.get(rid, {}))
                    self.state["rows"][rid] = {**old, "cells": {re.sub(r"^.*c", "c", c["id"]): c["text"] for c in row["cells"] if c["id"]},
                                               "run": old.get("run", uuid.uuid4().hex), "observed": old.get("observed", 0),
                                               "classes": {re.sub(r"^.*c", "c", c["id"]): c["class"] for c in row["cells"] if c["id"]},
                                               "sector_seen": old.get("sector_seen", {}),
                                               "position": row["position"]}
                    snapshots.add(rid)
            elif re.fullmatch(r"r\d+", target) and action in {"#", "pos"}:
                if target in self.state["rows"] and value.isdigit():
                    self.state["rows"][target]["position"] = int(value)
            elif re.fullmatch(r"r\d+", target) and action == "*":
                markers.add(target)
            elif re.fullmatch(r"r\d+", target) and action in {"*in", "*out"}:
                pits.add(target)
                row = self.state["rows"].get(target)
                if row is not None:
                    if action == "*in" and not row.get("in_pit"):
                        # Same-epoch gaps for a conservative pit-exit estimate.
                        row["pit_entry_field"] = [{k: r.get(k) for k in ("identity", "gapMs", "gapEstimated", "laps", "inPit")} for r in self.standings()]
                        row.update(in_pit=True, pit_enter_ms=clock_ms, pit_dirty=True, pit_exit_pending=False)
                        clean = row.get("recent_laps", [])[-3:]
                        row["pit_pace_ms"] = int(median(v["timeMs"] for v in clean)) if clean else None
                    elif action == "*out":
                        if row.get("in_pit"):
                            row["last_pit_ms"] = clock_ms - row["pit_enter_ms"]
                            row["last_pit_exit_ms"] = clock_ms
                            row["pit_exit_pending"] = True
                            row["completed_pits"] = row.get("completed_pits", 0) + 1
                            row["pit_sample_pending"] = True
                        row["in_pit"] = False
            elif re.fullmatch(r"r\d+c\d+", target):
                rid, col = target.split("c")
                row = self.state["rows"].get(rid)
                if row is not None:
                    row["cells"]["c" + col] = text(value)
                    row.setdefault("classes", {})["c" + col] = action
                    if self.state["headers"].get("c" + col) == "llp":
                        updated.add(rid)
                    kind = self.state["headers"].get("c" + col)
                    if kind in {"s1", "s2", "s3"} and "ib" not in action.split():
                        duration = milliseconds(text(value))
                        if duration is not None:
                            sector_updates.append((rid, kind.upper(), duration))
        self.state["clockMs"] = clock_ms
        passages = []
        if not self.supported:
            return passages
        # Display handoff is a physical passage, independent of whether its time
        # is excluded from clean personal bests after a pit stop.
        candidates = {rid for rid, _, _ in sector_updates}
        if not self.sector_ids():
            candidates |= updated  # Lap-only circuits: next actual lap crossing.
        for rid in candidates - snapshots - pits:
            row = self.state["rows"].get(rid)
            if not row or row.get("in_pit") or not row.get("pit_exit_pending"):
                continue
            if self.entrant(rid, row)["identity"] != identities.get(rid):
                continue
            before, after = prior.get(rid, ""), self.field(row, "tlp")
            if before.isdigit() and after.isdigit() and int(after) < int(before):
                continue
            if not self.sector_ids() and not (after.isdigit() and before.isdigit() and int(after)>int(before) or rid in markers):
                continue
            if clock_ms > row.get("last_pit_exit_ms", clock_ms):
                row["pit_exit_pending"] = False
        for rid, metric, duration in sector_updates:
            row = self.state["rows"][rid]
            if rid in snapshots or rid in pits or row.get("in_pit") or row.get("pit_dirty") or self.entrant(rid, row)["identity"] != identities.get(rid):
                continue
            after, before = self.field(row, "tlp"), prior.get(rid, "")
            if after.isdigit() and before.isdigit() and int(after) < int(before):
                continue
            counter_known = after.isdigit()
            completed = counter_known and before.isdigit() and int(after) > int(before) and rid in updated
            number = int(after) + (0 if metric == self.sector_ids()[-1] and completed else 1) if counter_known else row.get("observed", 0) + 1
            seen = row.setdefault("sector_seen", {})
            if seen.get(metric) == number:
                continue
            seen[metric] = number
            bests = row.setdefault("sector_bests", {})
            bests[metric] = min(bests.get(metric, duration), duration)
            passages.append({**self.entrant(rid, row), "metric": metric, "lap": number,
                             "lapCountKnown": counter_known, "timeMs": duration, "gap": False,
                             "validity": "unknown", "receivedAt": packet["receivedAt"]})
        for rid, row in self.state["rows"].items():
            before, after = prior.get(rid, ""), self.field(row, "tlp")
            old_count = baseline.get(rid, "")
            if old_count.isdigit() and after.isdigit() and int(after) < int(old_count):
                row["run"] = uuid.uuid4().hex
                for field in ("recent_laps", "pit_samples", "in_pit", "pit_enter_ms", "pit_dirty", "pit_sample_pending", "completed_pits", "sector_seen", "last_pit_ms", "last_pit_exit_ms", "pit_exit_pending", "pit_entry_field", "sector_bests", "observed_best_lap", "lap_crossings", "training_times", "training_latest_metric"):
                    row.pop(field, None)
            if rid in snapshots or rid not in updated:
                continue
            counter_known = "tlp" in self.state["headers"].values()
            if counter_known:
                if not before.isdigit() or not after.isdigit() or int(after) <= int(before):
                    continue
                number, gap = int(after), int(after) - int(before) > 1
            else:
                # Verified Spa race layout has no lap counter. '*' confirms a passage,
                # but its time is NOT necessarily the last-lap time. Count observed
                # passages explicitly; never present that count as the official lap.
                if rid not in markers:
                    continue
                number, gap = row.get("observed", 0) + 1, False
            if self.entrant(rid, row)["identity"] != identities.get(rid):
                continue
            duration = milliseconds(self.field(row, "llp"))
            if duration is not None:
                row["observed"] = number
                if counter_known:
                    crossings = row.setdefault("lap_crossings", {})
                    crossings[str(number)] = clock_ms
                    row["lap_crossings"] = dict(sorted(crossings.items(), key=lambda pair: int(pair[0]))[-16:])
                pit_lap = bool(row.get("pit_dirty") or row.get("in_pit"))
                if row.pop("pit_sample_pending", False):
                    pace, pit = row.get("pit_pace_ms"), row.get("last_pit_ms")
                    if pace and pit:
                        loss = duration - pace
                        fraction = (pit - loss) / pace
                        if loss > 0 and 0 <= fraction <= 0.8:
                            row["pit_samples"] = (row.get("pit_samples", []) + [{"lossMs": loss, "pitMs": pit, "paceMs": pace, "bypassFraction": fraction}])[-5:]
                if not pit_lap:
                    row["observed_best_lap"] = min(row.get("observed_best_lap", duration), duration)
                    row["recent_laps"] = (row.get("recent_laps", []) + [{"timeMs": duration, "kart": self.field(row, "no"), "atMs": clock_ms}])[-12:]
                if not row.get("in_pit"):
                    row["pit_dirty"] = False
                passages.append({**self.entrant(rid, row), "metric": "lap", "lap": number,
                                 "lapCountKnown": counter_known, "timeMs": duration, "gap": gap, "pitLap": pit_lap,
                                 "validity": "unknown", "receivedAt": packet["receivedAt"]})
        for rid in snapshots:
            row = self.state["rows"].get(rid)
            if row is None or row.get("in_pit") or row.get("pit_dirty"):
                continue
            self.entrant(rid, row)  # Clear another driver's cached values before seeding.
            status_col = next((col for col, kind in self.state["headers"].items() if kind == "sta"), None)
            if set(row.get("classes", {}).get(status_col, "").split()) & {"si", "so"}:
                continue
            for metric in self.sector_ids():
                duration = milliseconds(self.field(row, metric.lower()))
                if duration:
                    bests = row.setdefault("sector_bests", {})
                    bests[metric] = min(bests.get(metric, duration), duration)
        for passage in passages:
            row = self.state["rows"][passage["row"]]
            metric = passage["metric"]
            reference = training_references.get(passage["row"], {}).get(metric)
            _, value = delta_feedback({metric: reference} if reference is not None else {}, metric, passage["timeMs"])
            if passage.get("pitLap"):
                value.update(deltaMs=None, pitLap=True)
            value.update(lap=passage["lap"], kart=passage["kart"], receivedAt=stamp)
            row.setdefault("training_times", {})[metric] = value
            row["training_latest_metric"] = metric
        self.state["session_best_times"] = self.session_bests()
        self.state["session_records"] = self.session_records()
        return passages
