"""Latest device state; sensor history belongs in a later retention-aware logger."""
from django.conf import settings
from django.db import models


class TelemetryDevice(models.Model):
    device_id = models.SlugField(max_length=64, unique=True)
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    token_digest = models.CharField(max_length=64)
    enabled = models.BooleanField(default=True)
    boot_id = models.CharField(max_length=64, blank=True)
    retired_boots = models.JSONField(default=list)
    last_seq = models.BigIntegerField(default=-1)
    latest = models.JSONField(default=dict)
    received_at = models.DateTimeField(null=True)
    label = models.CharField(max_length=80, default="Kartdashboard")
    assigned_driver = models.ForeignKey("www.FollowDriver", null=True, blank=True,
        on_delete=models.SET_NULL, related_name="dashboards")
    assignment_revision = models.PositiveIntegerField(default=0)
