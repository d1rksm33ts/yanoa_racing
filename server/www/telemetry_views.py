import hashlib
import hmac
import json

from django.db import transaction
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST

from .live_views import coach_access
from .live_models import FollowDriver
from .telemetry_timing import timing_for
from .telemetry_core import validate, project, DEVICE_ONLINE_MS
from .telemetry_models import TelemetryDevice


def response(data, status=200):
    result = JsonResponse(data, status=status)
    result["Cache-Control"] = "no-store"
    return result


@csrf_exempt  # Machine-only endpoint: independent per-device bearer; cookies never authorize writes.
@never_cache
@require_POST
def ingest(request, device_id):
    authorization = request.headers.get("Authorization", "")
    if not authorization.startswith("Bearer ") or len(authorization) > 256:
        return response({"error": "Device credentials required"}, 401)
    digest = hashlib.sha256(authorization[7:].encode()).hexdigest()
    with transaction.atomic():
        device = TelemetryDevice.objects.select_for_update().filter(device_id=device_id, enabled=True).first()
        if (device is None or not hmac.compare_digest(device.token_digest, digest)
                or not device.owner.is_active or not device.owner.has_perm("www.use_livecoach")):
            return response({"error": "Device credentials required"}, 401)
        if request.content_type != "application/json":
            return response({"error": "JSON required"}, 415)
        # Bound request reading even if Content-Length is absent or dishonest.
        raw = request.read(4097)
        if len(raw) > 4096:
            return response({"error": "Frame too large"}, 413)
        try:
            data = validate(json.loads(raw), device_id)
        except (ValueError, TypeError, KeyError, UnicodeDecodeError, RecursionError):
            return response({"error": "Invalid telemetry v1"}, 400)
        boot, seq = data["boot_id"], data["seq"]
        if boot in device.retired_boots or (boot == device.boot_id and seq <= device.last_seq):
            return response({"accepted": False, "reason": "old_or_duplicate"}, 409)
        if boot == device.boot_id and device.latest and data["uptime_ms"] < device.latest["uptime_ms"]:
            return response({"accepted": False, "reason": "uptime_regression"}, 409)
        now = timezone.now()
        if device.received_at and (now - device.received_at).total_seconds() < .1:
            return response({"accepted": False, "reason": "rate_limit"}, 429)
        if boot != device.boot_id and device.boot_id:
            if len(device.retired_boots) >= 64:
                return response({"error": "Reprovision device after 64 reboots"}, 409)
            device.retired_boots = [*device.retired_boots, device.boot_id]
        device.boot_id, device.last_seq = boot, seq
        device.latest, device.received_at = data, now
        device.save(update_fields=["boot_id", "last_seq", "retired_boots", "latest", "received_at"])
    device = TelemetryDevice.objects.select_related("assigned_driver__session__track").get(pk=device.pk)
    return response({"accepted": True, "seq": seq, "timing": timing_for(device)}, 202)


@coach_access
@require_GET
def detail(request, device_id):
    device = get_object_or_404(TelemetryDevice, device_id=device_id, owner=request.user)
    return response(project(device, timezone.now()))


@coach_access
@require_GET
def devices(request):
    now = timezone.now()
    result = []
    qs = TelemetryDevice.objects.filter(owner=request.user).select_related("assigned_driver__session__track")
    for device in qs.order_by("label", "device_id"):
        state = project(device, now)
        result.append({**state, "label": device.label, "timing": timing_for(device, now),
                       "assigned_driver_id": device.assigned_driver_id})
    drivers = FollowDriver.objects.filter(session__owner=request.user, session__state="active").select_related("session__track").order_by("session__name", "name")
    return response({"devices": result, "drivers": [{"id": d.pk, "name": d.name, "kart": d.kart,
        "session": d.session.name, "session_id": str(d.session_id), "identity": d.identity, "activity": d.session.activity, "source": "REPLAY" if d.session.track.mode == "replay" else "LIVE"}
        for d in drivers]})


@coach_access
@require_POST
@transaction.atomic
def assign(request, device_id):
    device = get_object_or_404(TelemetryDevice.objects.select_for_update(), device_id=device_id, owner=request.user)
    if request.content_type != "application/json" or len(request.body) > 1024:
        return response({"error": "Ongeldige aanvraag"}, 400)
    data = json.loads(request.body)
    if not isinstance(data, dict) or set(data) != {"driver_id"}:
        return response({"error": "Kies een piloot"}, 400)
    driver_id = data["driver_id"]
    driver = None
    if driver_id is not None:
        if type(driver_id) is not int:
            return response({"error": "Kies een piloot"}, 400)
        driver = get_object_or_404(FollowDriver, pk=driver_id, session__owner=request.user, session__state="active")
        if not device.enabled or not device.received_at or (timezone.now() - device.received_at).total_seconds() * 1000 > DEVICE_ONLINE_MS:
            return response({"error": "Het dashboard is offline. Wacht op de verbinding."}, 409)
    if device.assigned_driver_id != driver_id:
        device.assigned_driver = driver
        device.assignment_revision += 1
        device.save(update_fields=["assigned_driver", "assignment_revision"])
    return response({"device_id": device.device_id, "assigned_driver_id": device.assigned_driver_id,
                     "timing": timing_for(device)})
