"""Transport-neutral telemetry v1 validation and freshness projection."""
import copy
import math
import re

DEVICE_ONLINE_MS = 15000
HEARTBEAT_DELAYED_MS = 3000

ID = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
POSITION = {"lat_deg": (-90, 90), "lon_deg": (-180, 180), "speed_mps": (0, 200),
            "heading_deg": (0, 360), "h_accuracy_m": (0, 1000000)}


def integer(value, low=0, high=2**53 - 1):
    if type(value) is not int or not low <= value <= high:
        raise ValueError("Invalid integer")
    return value


def identifier(value):
    if not isinstance(value, str) or not ID.fullmatch(value):
        raise ValueError("Invalid identifier")
    return value


def validate(data, device_id):
    if not isinstance(data, dict) or type(data.get("schema_version")) is not int or data["schema_version"] != 1:
        raise ValueError("Unsupported schema")
    if data.get("device_id") != device_id:
        raise ValueError("Wrong device")
    identifier(data["device_id"])
    identifier(data.get("boot_id"))
    integer(data.get("seq"), high=2**32 - 1)
    integer(data.get("uptime_ms"))
    # Assignment is server metadata; sample-level UTC synchronization is not implemented.
    if data.get("session_id") is not None or data.get("sample_ts_ms") is not None:
        raise ValueError("Sensor frames use server assignment and no sample UTC")
    g = data.get("gnss")
    if not isinstance(g, dict) or type(g.get("valid")) is not bool:
        raise ValueError("GNSS required")
    for name, (low, high) in POSITION.items():
        value = g.get(name)
        if not g["valid"]:
            if value is not None:
                raise ValueError("Invalid position must be null")
        elif type(value) not in (int, float) or not math.isfinite(value) or not low <= value <= high:
            raise ValueError("Invalid GNSS value")
    for name, high in (("satellites", 255), ("fix_type", 5), ("itow_ms", 604799999), ("age_ms", 2**32 - 1)):
        if g.get(name) is not None:
            integer(g[name], high=high)
    if g["valid"] and (g.get("age_ms") is None or g["age_ms"] > 1000):
        raise ValueError("Position is not fresh")
    if g["valid"] and g.get("fix_type") not in (2, 3, 4):
        raise ValueError("Position requires a fix")
    imu = data.get("imu")
    if (not isinstance(imu, dict) or set(imu) != {"valid", "accel_mps2", "gyro_dps", "frame"}
            or type(imu.get("valid")) is not bool or imu.get("frame") != "sensor"):
        raise ValueError("Invalid IMU")
    for field, limit in (("accel_mps2", 160), ("gyro_dps", 2000)):
        values = imu.get(field)
        if not imu["valid"]:
            if values is not None:
                raise ValueError("Invalid IMU must be null")
        elif (not isinstance(values, list) or len(values) != 3
                or any(type(v) not in (int, float) or not math.isfinite(v) or abs(v) > limit for v in values)):
            raise ValueError("Invalid IMU vector")
    if data.get("local_timing") != {"valid": False, "delta_ms": None}:
        raise ValueError("Local timing not implemented")
    if data.get("battery_pct") is not None or data.get("lte_rssi_dbm") is not None:
        raise ValueError("Battery/LTE not implemented")
    diagnostics = data.get("diagnostics", {})
    if not isinstance(diagnostics, dict) or set(diagnostics) - {"pvt_frames", "ubx_checksum_errors", "interval_ms", "gap_events"}:
        raise ValueError("Invalid diagnostics")
    for value in diagnostics.values():
        integer(value, high=2**32 - 1)
    allowed = {"schema_version", "device_id", "session_id", "boot_id", "seq", "sample_ts_ms", "uptime_ms",
               "gnss", "imu", "local_timing", "battery_pct", "lte_rssi_dbm", "diagnostics"}
    if set(data) - allowed or set(g) - (set(POSITION) | {"valid", "satellites", "fix_type", "itow_ms", "age_ms"}):
        raise ValueError("Unknown fields")
    return copy.deepcopy(data)


def project(device, now):
    data = copy.deepcopy(device.latest)
    age = None if device.received_at is None else max(0, int((now - device.received_at).total_seconds() * 1000))
    if data:
        g = data["gnss"]
        sample_age = g.get("age_ms")
        if sample_age is not None:
            g["age_ms"] = sample_age + age
        if not device.enabled or age > 1000:
            data["imu"].update(valid=False, accel_mps2=None, gyro_dps=None)
        if not device.enabled or age > 1000 or sample_age is None or g["age_ms"] > 1000:
            g["valid"] = False
            for key in POSITION:
                g[key] = None
            g["satellites"] = g["fix_type"] = g["itow_ms"] = None
    return {"device_id": device.device_id, "online": device.enabled and age is not None and age <= DEVICE_ONLINE_MS,
            "connection_status": "offline" if not device.enabled or age is None or age > DEVICE_ONLINE_MS else "delayed" if age > HEARTBEAT_DELAYED_MS else "online",
            "server_received_ts_ms": None if device.received_at is None else int(device.received_at.timestamp() * 1000),
            "receipt_age_ms": age, "telemetry": data or None}
