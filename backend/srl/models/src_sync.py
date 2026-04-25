from django.db import models


class SRCSyncTask(models.Model):
    class Meta:
        verbose_name = "SRC Sync Task"
        verbose_name_plural = "SRC Sync Tasks"
        indexes = [
            models.Index(
                fields=["status"],
                name="idx_srcsync_status",
            ),
            models.Index(
                fields=["run", "status"],
                name="idx_srcsync_run_status",
            ),
        ]

    class ActionType(models.TextChoices):
        VERIFY = "verify", "Verify"
        REJECT = "reject", "Reject"
        CHANGE_PLAYERS = "change_players", "Change Players"

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        SYNCED = "synced", "Synced"
        FAILED = "failed", "Failed"

    run = models.ForeignKey(
        "srl.Runs",
        on_delete=models.CASCADE,
        related_name="sync_tasks",
    )
    action = models.CharField(
        max_length=20,
        choices=ActionType.choices,
    )
    status = models.CharField(
        max_length=10,
        choices=Status.choices,
        default=Status.PENDING,
    )
    payload = models.JSONField(
        help_text="The JSON body to send to the SRC API.",
    )
    moderator = models.ForeignKey(
        "srl.Players",
        on_delete=models.PROTECT,
        null=True,
        related_name="src_sync_tasks",
    )
    attempts = models.PositiveSmallIntegerField(default=0)
    max_attempts = models.PositiveSmallIntegerField(default=5)
    last_error = models.TextField(
        blank=True,
        default="",
        help_text="Error details from the most recent failed attempt.",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(
        self,
    ) -> str:
        return f"SRCSync {self.action} run={self.run_id} [{self.status}]"
