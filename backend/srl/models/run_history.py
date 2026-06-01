from django.db import models

from srl.models.runs import Runs


class RunHistoryEndReason(models.TextChoices):
    NEW_WR = "new_wr", "New World Record"
    LOST_WR = "lost_wr", "Lost World Record"
    GAINED_WR = "gained_wr", "Gained World Record"
    OBSOLETED = "obsoleted", "Run Obsoleted"
    RECALCULATION = "recalculation", "Points Recalculated"


class RunHistory(models.Model):
    class Meta:
        verbose_name = "Run History"
        verbose_name_plural = "Run History"
        ordering = ["start_date"]
        indexes = [
            models.Index(fields=["start_date", "end_date"]),
            models.Index(fields=["run", "start_date"]),
        ]

    run = models.ForeignKey(
        Runs,
        on_delete=models.CASCADE,
        related_name="history",
        verbose_name="Run",
    )
    start_date = models.DateTimeField(
        verbose_name="Period Start",
    )
    end_date = models.DateTimeField(
        verbose_name="Period End",
        null=True,
        blank=True,
    )
    points = models.PositiveSmallIntegerField(
        verbose_name="Points During Period",
    )
    end_reason = models.CharField(
        max_length=20,
        choices=RunHistoryEndReason.choices,
        null=True,
        blank=True,
        verbose_name="End Reason",
    )
    streak_start_date = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Streak Start (WR entries only)",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    constraints = [
        models.UniqueConstraint(
            fields=["run"],
            condition=models.Q(end_date__isnull=True),
            name="unique_open_runhistory_per_run",
        ),
    ]

    def __str__(
        self,
    ) -> str:
        end = self.end_date.strftime("%Y-%m-%d") if self.end_date else "present"
        return f"{self.run.id}: {self.start_date.strftime('%Y-%m-%d')} - {end} ({self.points} pts)"
