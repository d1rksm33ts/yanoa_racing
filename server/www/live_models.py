"""Durable state for Live Coach; imported by www.models for Django discovery."""
import uuid

from django.conf import settings
from django.db import models


class TimingTrack(models.Model):
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT)
    slug = models.SlugField(unique=True)
    name = models.CharField(max_length=100)
    source_id = models.CharField(max_length=30)
    mode = models.CharField(max_length=10, default="live")
    connection = models.CharField(max_length=30, default="offline")
    worker_at = models.DateTimeField(null=True)
    packet_at = models.DateTimeField(null=True)
    timing_at = models.DateTimeField(null=True)
    title = models.CharField(max_length=200, blank=True)
    parser_state = models.JSONField(default=dict)
    entrants = models.JSONField(default=list)
    capabilities = models.JSONField(default=dict)
    error = models.CharField(max_length=300, blank=True)

    class Meta:
        permissions = [("use_livecoach", "Can use Live Coach")]


class FollowSession(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    track = models.ForeignKey(TimingTrack, on_delete=models.PROTECT)
    name = models.CharField(max_length=120)
    state = models.CharField(max_length=12, default="active")
    started_at = models.DateTimeField(auto_now_add=True)
    stopped_at = models.DateTimeField(null=True)
    activity = models.CharField(max_length=12, default="sprint", db_default="sprint")
    pit_settings = models.JSONField(default=dict)
    request_id = models.UUIDField(default=uuid.uuid4, unique=True)


class FollowDriver(models.Model):
    session = models.ForeignKey(FollowSession, related_name="drivers", on_delete=models.CASCADE)
    identity = models.CharField(max_length=64)
    name = models.CharField(max_length=150)
    kart = models.CharField(max_length=30, blank=True)
    primary = models.BooleanField(default=False)
    pit_enabled = models.BooleanField(default=False, db_default=False)
    block = models.PositiveIntegerField(default=1)
    best = models.JSONField(default=dict)
    last = models.JSONField(default=dict)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["session", "identity"], name="coach_driver_unique")]


class CoachEvent(models.Model):
    """Immutable feedback/control history, also the durable SSE outbox."""
    session = models.ForeignKey(FollowSession, related_name="events", on_delete=models.CASCADE)
    driver = models.ForeignKey(FollowDriver, null=True, on_delete=models.CASCADE)
    kind = models.CharField(max_length=20)
    payload = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)
    raw_key = models.CharField(max_length=200, null=True, unique=True)


class CoachAction(models.Model):
    session = models.ForeignKey(FollowSession, on_delete=models.CASCADE)
    request_id = models.UUIDField(unique=True)
    action = models.CharField(max_length=20)


class TimingPacket(models.Model):
    """Deduplication/checkpoint index; original bytes remain in NDJSON."""
    key = models.CharField(max_length=100, unique=True)
    track = models.ForeignKey(TimingTrack, on_delete=models.CASCADE)
    received_at = models.DateTimeField()


class TimingConnection(models.Model):
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    track = models.ForeignKey(TimingTrack, on_delete=models.CASCADE)
    enabled = models.BooleanField(default=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["owner", "track"], name="coach_connection_unique")]


class TimingRecording(models.Model):
    name = models.CharField(max_length=150)
    path = models.CharField(max_length=500, unique=True)
    checksum = models.CharField(max_length=64)
    segments = models.JSONField(default=list)


class TimingSimulation(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    track = models.OneToOneField(TimingTrack, related_name="simulation", on_delete=models.CASCADE)
    recording = models.ForeignKey(TimingRecording, on_delete=models.PROTECT)
    segment = models.PositiveIntegerField()
    state = models.CharField(max_length=12, default="paused")
    speed = models.FloatField(default=1)
    position_ms = models.PositiveBigIntegerField(default=0)
    anchor_ms = models.PositiveBigIntegerField(default=0)
    anchor_at = models.DateTimeField(null=True)
    byte_offset = models.PositiveBigIntegerField()
    run = models.PositiveIntegerField(default=1)
    error = models.CharField(max_length=300, blank=True)
    request_id = models.UUIDField(unique=True)


class KartReport(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    track = models.ForeignKey(TimingTrack, on_delete=models.PROTECT)
    session = models.ForeignKey(FollowSession, null=True, on_delete=models.SET_NULL)
    pilot = models.CharField(max_length=150)
    kart = models.CharField(max_length=30)
    session_name = models.CharField(max_length=120)
    conditions = models.CharField(max_length=10)
    scores = models.JSONField(default=dict)
    template = models.JSONField(default=dict)
    timing = models.JSONField(default=dict)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    request_id = models.UUIDField(unique=True)
