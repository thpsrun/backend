import uuid

from django.db import models


class ReconScope(models.TextChoices):
    RUN = "RUN", "Run"
    LEADERBOARD = "LEADERBOARD", "Leaderboard"
    GAME = "GAME", "Game"


class ReconSourceOfTruth(models.TextChoices):
    SRC = "SRC", "Speedrun.com"
    THPS_RUN = "THPS_RUN", "thps.run"


class ReconStatus(models.TextChoices):
    PENDING = "PENDING", "Pending"
    RUNNING = "RUNNING", "Running"
    SUCCEEDED = "SUCCEEDED", "Succeeded"
    FAILED = "FAILED", "Failed"
    CANCELLED = "CANCELLED", "Cancelled"


class ReconPhase(models.TextChoices):
    PENDING = "PENDING", "Pending"
    P1 = "P1", "Phase 1: Surface Level"
    P2 = "P2", "Phase 2: Obsolete Backfill"
    P3 = "P3", "Phase 3: Recompute Leaderboards"


class ReconItemPhase(models.TextChoices):
    P1 = "P1", "Phase 1"
    P2 = "P2", "Phase 2"
    P3 = "P3", "Phase 3"


class ReconAction(models.TextChoices):
    CREATED = "CREATED", "Created"
    UPDATED = "UPDATED", "Updated"
    SKIPPED_LOCAL_WINS = "SKIPPED_LOCAL_WINS", "Skipped (local wins)"
    SKIPPED_NO_CHANGE = "SKIPPED_NO_CHANGE", "Skipped (no change)"
    FAILED = "FAILED", "Failed"

    @property
    def bucket(self) -> str | None:
        if self == ReconAction.CREATED:
            return "created"
        if self == ReconAction.UPDATED:
            return "updated"
        if self in (ReconAction.SKIPPED_LOCAL_WINS, ReconAction.SKIPPED_NO_CHANGE):
            return "skipped"
        if self == ReconAction.FAILED:
            return "failed"
        return None


class ReconciliationJob(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    scope = models.CharField(max_length=16, choices=ReconScope.choices)
    target_id = models.CharField(max_length=128, blank=True)
    target_descriptor = models.JSONField(default=dict, blank=True)
    source_of_truth = models.CharField(
        max_length=16,
        choices=ReconSourceOfTruth.choices,
        default=ReconSourceOfTruth.SRC,
    )
    status = models.CharField(
        max_length=16,
        choices=ReconStatus.choices,
        default=ReconStatus.PENDING,
    )
    phase = models.CharField(
        max_length=8,
        choices=ReconPhase.choices,
        default=ReconPhase.PENDING,
    )
    cancel_requested = models.BooleanField(default=False)
    requested_by = models.ForeignKey(
        "accounts.CustomUser",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="reconciliation_jobs",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    counts_created = models.IntegerField(default=0)
    counts_updated = models.IntegerField(default=0)
    counts_skipped = models.IntegerField(default=0)
    counts_failed = models.IntegerField(default=0)
    error_summary = models.TextField(blank=True, default="")
    celery_task_id = models.CharField(max_length=128, blank=True, default="")
    pending_children = models.IntegerField(default=0)
    failure_count = models.IntegerField(default=0)

    class Meta:
        indexes = [
            models.Index(fields=["scope", "target_id", "status"]),
            models.Index(fields=["-created_at"]),
        ]

    @property
    def counts(self) -> dict[str, int]:
        return {
            "created": self.counts_created,
            "updated": self.counts_updated,
            "skipped": self.counts_skipped,
            "failed": self.counts_failed,
        }


class ReconciliationItem(models.Model):
    job = models.ForeignKey(
        ReconciliationJob,
        on_delete=models.CASCADE,
        related_name="items",
    )
    record_type = models.CharField(max_length=64)
    record_id = models.CharField(max_length=128)
    action = models.CharField(max_length=32, choices=ReconAction.choices)
    phase = models.CharField(max_length=2, choices=ReconItemPhase.choices)
    changes = models.JSONField(default=dict, blank=True)
    error = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=["job", "action"]),
            models.Index(fields=["job", "phase"]),
        ]
