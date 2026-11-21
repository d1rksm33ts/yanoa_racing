import asyncio
import json
import time
import uuid
from functools import wraps

from asgiref.sync import sync_to_async
from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models import Q
from django.http import Http404, JsonResponse, StreamingHttpResponse
from django.shortcuts import get_object_or_404, render
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET, require_POST

from .live_models import CoachAction, FollowDriver, FollowSession, TimingTrack, TimingConnection, TimingRecording, TimingSimulation
from .live_simulation import create_simulation, control, simulation_data, SimulationLimitError
from .live_pit import settings_for, validate_settings
from .live_service import publish, seed_tracks, snapshot, track_data


def coach_access(view):
    @login_required(login_url="www:livecoach-login")
    @never_cache
    @wraps(view)
    def wrapped(request, *args, **kwargs):
        if not request.user.is_active or not request.user.has_perm("www.use_livecoach"):
            raise PermissionDenied
        try:
            return view(request, *args, **kwargs)
        except (ValueError, KeyError, TypeError, json.JSONDecodeError):
            return JsonResponse({"error": "Ongeldige aanvraag."}, status=400)
    return wrapped


def body(request):
    if len(request.body) > 8192 or request.content_type != "application/json":
        raise ValueError("JSON required")
    value = json.loads(request.body)
    if not isinstance(value, dict):
        raise ValueError("Object required")
    return value


def owned(request, pk, lock=False):
    qs = FollowSession.objects.select_related("track").filter(owner=request.user)
    if lock:
        # Avoid PostgreSQL locking the joined track and conflicting with worker order.
        qs = qs.select_for_update(of=("self",))
    return get_object_or_404(qs, pk=pk)


@coach_access
@require_GET
def page(request, activity=None):
    if activity is None:
        return render(request, "livecoach/choose.html")
    if activity not in {"training", "sprint", "endurance"}:
        raise Http404
    return render(request, "livecoach/index.html", {"coach_mode": activity})


@coach_access
@require_GET
def summary(request):
    sessions = FollowSession.objects.filter(owner=request.user).select_related("track").prefetch_related("drivers").order_by("-started_at")[:50]
    return render(request, "livecoach/summary.html", {"sessions": sessions})


@coach_access
@require_GET
def overview(request):
    seed_tracks()
    enabled = set(TimingConnection.objects.filter(owner=request.user, enabled=True).values_list("track_id", flat=True))
    tracks = []
    for track in TimingTrack.objects.filter(Q(owner__isnull=True) | Q(owner=request.user)).order_by("name"):
        data = track_data(track)
        data["subscribed"] = track.pk in enabled
        if not data["subscribed"]:
            data.update(entrants=[], standings=[], connection="disconnected")
        tracks.append(data)
    simulations = TimingSimulation.objects.filter(owner=request.user).select_related("recording")
    visible_simulations = list(simulations.filter(state__in=["paused", "playing", "rewinding"]).order_by("-track_id"))
    visible_simulations += list(simulations.exclude(state__in=["paused", "playing", "rewinding"]).order_by("-track_id")[:20])
    return JsonResponse({"tracks": tracks,
                         "activeSessions": [{"id": str(s.pk), "name": s.name, "track": s.track.name, "trackId": s.track_id,
                              "startedAt": s.started_at.isoformat(), "drivers": [d.name for d in s.drivers.all()]}
                             for s in FollowSession.objects.filter(owner=request.user, state="active").select_related("track").prefetch_related("drivers").order_by("started_at")],
                         "recordings": [{"id": r.pk, "name": r.name, "segments": [
                             {"index": i, "title": s["title"], "durationMs": max(0, s["endMs"] - s["startMs"]),
                              "drivers": [d["name"] for d in s["drivers"]]} for i, s in enumerate(r.segments)]}
                              for r in TimingRecording.objects.order_by("name")],
                         "simulations": [simulation_data(s) for s in visible_simulations],
                         "sessions": [{"id": str(s.pk), "name": s.name, "state": s.state,
                                       "track": s.track.name} for s in FollowSession.objects.filter(owner=request.user).select_related("track").order_by("-started_at")[:50]]})


@coach_access
@require_POST
@transaction.atomic
def connect(request):
    data = body(request)
    track = get_object_or_404(TimingTrack.objects.filter(Q(owner__isnull=True) | Q(owner=request.user)), pk=data["trackId"])
    enabled = data["action"] == "connect"
    if data["action"] not in {"connect", "disconnect"}:
        raise ValueError("Invalid connection action")
    if not enabled and FollowSession.objects.filter(owner=request.user, track=track, state="active").exists():
        return JsonResponse({"error": "Stop eerst je actieve volgsessie op deze baan."}, status=409)
    TimingConnection.objects.update_or_create(owner=request.user, track=track, defaults={"enabled": enabled})
    return JsonResponse({"subscribed": enabled, "track": track_data(track)})


@coach_access
@require_POST
def simulate(request):
    data = body(request)
    recording = get_object_or_404(TimingRecording, pk=data["recordingId"])
    segment = int(data["segment"])
    if not 0 <= segment < len(recording.segments):
        raise ValueError("Invalid segment")
    request_id = uuid.UUID(data["requestId"])
    if TimingSimulation.objects.filter(request_id=request_id).exclude(owner=request.user).exists():
        raise Http404
    try:
        simulation = create_simulation(request.user, recording, segment, request_id)
    except SimulationLimitError as error:
        return JsonResponse({"error": str(error)}, status=409)
    return JsonResponse(simulation_data(simulation), status=201)


@coach_access
@require_POST
def simulation_action(request, pk):
    get_object_or_404(TimingSimulation, pk=pk, owner=request.user)
    data = body(request)
    return JsonResponse(simulation_data(control(pk, request.user, data["action"], speed=data.get("speed"))))


@coach_access
@require_POST
@transaction.atomic
def start(request):
    data = body(request)
    request_id = uuid.UUID(data["requestId"])
    existing = FollowSession.objects.filter(request_id=request_id).first()
    if existing:
        if existing.owner_id != request.user.pk:
            raise Http404
        return JsonResponse(snapshot(existing))
    track = get_object_or_404(TimingTrack.objects.select_for_update().filter(Q(owner__isnull=True) | Q(owner=request.user)), pk=data["trackId"])
    existing = FollowSession.objects.filter(request_id=request_id).first()
    if existing:
        if existing.owner_id != request.user.pk:
            raise Http404
        return JsonResponse(snapshot(existing))
    status = track_data(track)
    if not TimingConnection.objects.filter(owner=request.user, track=track, enabled=True).exists():
        return JsonResponse({"error": "Verbind eerst met deze baan."}, status=409)
    if not status["workerActive"] or status["connection"] != "connected" or not track.capabilities.get("laps"):
        return JsonResponse({"error": "De bron is nog niet klaar voor rondefeedback."}, status=409)
    activity = data.get("activity", "sprint")
    if activity not in {"training", "sprint", "endurance"}:
        raise ValueError("Invalid activity")
    selected = data["drivers"]
    if activity == "training" and (not isinstance(selected, list) or len(selected) != 1):
        return JsonResponse({"error": "Kies één piloot voor deze training."}, status=400)
    available = {e["identity"]: e for e in track.entrants}
    if not isinstance(selected, list) or not 1 <= len(selected) <= 12 or len(set(selected)) != len(selected) or any(e not in available for e in selected):
        raise ValueError("Invalid drivers")
    if FollowSession.objects.filter(owner=request.user, state="active").count() >= 5:
        return JsonResponse({"error": "Je hebt vijf actieve volgsessies. Open bovenaan Actieve volgsessies en kies Stop & bewaar bij een sessie."}, status=409)
    name = str(data.get("name", "")).strip()[:120] or track.name
    session = FollowSession.objects.create(owner=request.user, track=track, name=name, request_id=request_id, activity=activity, pit_settings=settings_for(track))
    for i, identity in enumerate(selected):
        entrant = available[identity]
        FollowDriver.objects.create(session=session, identity=identity, name=entrant["name"][:150], kart=entrant["kart"][:30], primary=i == 0)
    publish(session, "started", {"message": "Volgsessie gestart; eerste nieuwe ronde zet de referentie."})
    return JsonResponse(snapshot(session), status=201)


@coach_access
@require_GET
def detail(request, pk):
    return JsonResponse(snapshot(owned(request, pk)))


@coach_access
@require_POST
@transaction.atomic
def discard(request, pk):
    session = owned(request, pk, lock=True)
    if session.state != "active":
        return JsonResponse({"error": "Deze volgsessie is al gestopt."}, status=409)
    identity = str(session.pk)
    session.delete()  # Cascades only its own drivers, feedback and action history.
    return JsonResponse({"discarded": identity})


@coach_access
@require_POST
@transaction.atomic
def action(request, pk):
    data = body(request)
    session = owned(request, pk, lock=True)
    request_id = uuid.UUID(data["requestId"])
    previous = CoachAction.objects.filter(request_id=request_id).first()
    if previous:
        if previous.session_id != session.pk:
            raise Http404
        return JsonResponse(snapshot(session))
    name = data["action"]
    if name not in {"stop", "reset", "save", "drivers", "pit", "driver-pit"}:
        raise ValueError("Unknown action")
    if name in {"stop", "reset", "drivers", "pit", "driver-pit"} and session.state != "active":
        return JsonResponse({"error": "Deze sessie is al gestopt."}, status=409)
    if name == "stop":
        session.state = "stopped"
        session.stopped_at = timezone.now()
        session.save(update_fields=["state", "stopped_at"])
    elif name == "reset":
        drivers = session.drivers.select_for_update()
        if data.get("driverId") is not None:
            drivers = drivers.filter(pk=int(data["driverId"]))
        drivers = list(drivers)
        if not drivers:
            raise ValueError("Unknown driver")
        for driver in drivers:
            driver.block += 1
            driver.best = {}
            driver.last = {}
            driver.save(update_fields=["block", "best", "last"])
    elif name == "drivers":
        selected = data["drivers"]
        if session.activity == "training" and (not isinstance(selected, list) or len(selected) != 1):
            raise ValueError("Training requires one driver")
        available = {e["identity"]: e for e in session.track.entrants}
        if not isinstance(selected, list) or not 1 <= len(selected) <= 12 or len(set(selected)) != len(selected) or any(e not in available for e in selected):
            raise ValueError("Invalid selection")
        session.drivers.exclude(identity__in=selected).delete()
        for index, identity in enumerate(selected):
            entrant = available[identity]
            driver, created = FollowDriver.objects.get_or_create(session=session, identity=identity,
                defaults={"name": entrant["name"][:150], "kart": entrant["kart"][:30], "primary": index == 0})
            if not created and driver.primary != (index == 0):
                driver.primary = index == 0
                driver.save(update_fields=["primary"])
    elif name == "driver-pit":
        if type(data["enabled"]) is not bool:
            raise ValueError("Boolean required")
        driver = get_object_or_404(session.drivers.select_for_update(), pk=int(data["driverId"]))
        driver.pit_enabled = data["enabled"]
        driver.save(update_fields=["pit_enabled"])
    elif name == "pit":
        session.pit_settings = validate_settings(data["settings"])
        session.save(update_fields=["pit_settings"])
    elif name == "save":
        session.name = str(data["name"]).strip()[:120]
        if not session.name:
            raise ValueError("Empty name")
        session.save(update_fields=["name"])
    CoachAction.objects.create(session=session, request_id=request_id, action=name)
    publish(session, name, {"driverId": data.get("driverId"), "message": {"stop": "Sessie gestopt en bewaard.", "reset": "Nieuw referentieblok; eerdere tijden blijven bewaard.", "save": "Naam opgeslagen.", "pit": "Pitinstellingen opgeslagen.", "driver-pit": "Pitvoorspelling bijgewerkt.", "drivers": "Piloten bijgewerkt; referenties van behouden piloten zijn bewaard."}[name]})
    return JsonResponse(snapshot(session))


@coach_access
@require_GET
def export(request, pk):
    session = owned(request, pk)
    response = JsonResponse({"session": snapshot(session), "events": list(session.events.order_by("pk").values("id", "kind", "payload", "created_at"))})
    response["Content-Disposition"] = f'attachment; filename="livecoach-{session.pk}.json"'
    return response


@coach_access
@require_GET
def stream(request, pk):
    owned(request, pk)
    user_id = request.user.pk

    def read():
        from django.contrib.auth import get_user_model
        user = get_user_model().objects.get(pk=user_id)
        if not user.is_active or not user.has_perm("www.use_livecoach"):
            return None
        session = FollowSession.objects.select_related("track").filter(pk=pk, owner_id=user_id).first()
        return snapshot(session) if session else None

    async def events():
        # Durable snapshots make reconnect safe: no queued audio or repeated live alerts.
        # PostgreSQL NOTIFY is a wake-up only; SQLite uses a short development interval.
        db = settings.DATABASES["default"]
        listener = None
        try:
            if db["ENGINE"].endswith("postgresql"):
                import psycopg
                listener = await psycopg.AsyncConnection.connect(dbname=db["NAME"], user=db["USER"], password=db["PASSWORD"], host=db["HOST"], port=db["PORT"], autocommit=True, connect_timeout=5)
                await listener.execute("LISTEN livecoach")
            previous = None
            last_sent = 0
            deadline = time.monotonic() + 60
            yield "retry: 1000\n\n"
            while time.monotonic() < deadline:
                state = await sync_to_async(read, thread_sensitive=True)()
                if state is None:
                    yield 'event: revoked\ndata: {}\n\n'
                    return
                data = json.dumps(state, separators=(",", ":"))
                if data != previous or time.monotonic() - last_sent >= 10:
                    yield f"id: {state['cursor']}\nevent: snapshot\ndata: {data}\n\n"
                    previous, last_sent = data, time.monotonic()
                if listener:
                    async for _ in listener.notifies(timeout=1, stop_after=1):
                        pass
                else:
                    await asyncio.sleep(0.1)
        finally:
            if listener:
                await listener.close()

    response = StreamingHttpResponse(events(), content_type="text/event-stream")
    response["Cache-Control"] = "no-store, no-transform"
    response["X-Accel-Buffering"] = "no"
    return response


@coach_access
@require_GET
def kart_reports(request):
    from .live_models import KartReport
    from .live_training import SCORE_TEMPLATE, report_data
    reports = KartReport.objects.filter(owner=request.user).select_related("track").order_by("-created_at")
    if request.GET.get("trackId"):
        reports = reports.filter(track_id=int(request.GET["trackId"]))
    if request.GET.get("kart"):
        reports = reports.filter(kart=request.GET["kart"][:30])
    return JsonResponse({"template": SCORE_TEMPLATE, "reports": [report_data(item) for item in reports[:200]]})


@coach_access
@require_POST
@transaction.atomic
def save_kart_report(request, pk):
    from .live_models import KartReport
    from .live_training import SCORE_TEMPLATE, used_karts, kart_timing, report_data
    session = owned(request, pk, lock=True)
    data = body(request)
    request_id = uuid.UUID(data["requestId"])
    existing = KartReport.objects.filter(request_id=request_id).first()
    if existing:
        if existing.owner_id != request.user.pk or existing.session_id != session.pk:
            raise Http404
        return JsonResponse(report_data(existing))
    driver = get_object_or_404(session.drivers, pk=int(data["driverId"]))
    kart = str(data["kart"])
    if kart not in used_karts(session, driver):
        raise ValueError("Kart not used by this driver")
    track = get_object_or_404(TimingTrack, pk=int(data["trackId"]), owner__isnull=True, mode="live")
    if session.track.mode == "live" and track.pk != session.track_id:
        raise ValueError("Different circuit")
    scores = data["scores"]
    keys = {item["id"] for item in SCORE_TEMPLATE["elements"]}
    if not isinstance(scores, dict) or not scores or not set(scores) <= keys or any(type(value) is not int or not 1 <= value <= 5 for value in scores.values()):
        raise ValueError("Use scores 1–5")
    conditions = data["conditions"]
    if conditions not in {"dry", "damp", "wet"}:
        raise ValueError("Invalid conditions")
    notes = data.get("notes", "")
    if not isinstance(notes, str) or len(notes) > 2000:
        raise ValueError("Notes too long")
    report = KartReport.objects.create(owner=request.user, track=track, session=session,
        pilot=driver.name, kart=kart, session_name=session.name, conditions=conditions, scores=scores,
        notes=notes.strip(), template=SCORE_TEMPLATE, timing=kart_timing(session, driver, kart), request_id=request_id)
    return JsonResponse(report_data(report), status=201)
