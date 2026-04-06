from django.db import models


class RunPlayers(models.Model):
    class Meta:
        verbose_name = "Run Player"
        verbose_name_plural = "Run Players"
        constraints = [
            models.UniqueConstraint(
                fields=["run", "player"],
                name="unique_run_player",
            )
        ]
        indexes = [
            models.Index(
                fields=["player", "run"],
                name="idx_runplayers_player_run",
            ),
        ]
        ordering = ["run", "order"]

    run = models.ForeignKey(
        "Runs", on_delete=models.CASCADE, related_name="run_players"
    )
    player = models.ForeignKey(
        "Players", on_delete=models.CASCADE, related_name="player_runs"
    )

    order = models.PositiveSmallIntegerField(
        default=1,
        help_text="Order of this player in the run (1 for primary player, 2 for secondary, etc.)",
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
        null=True,
    )
    updated_at = models.DateTimeField(
        auto_now=True,
    )

    def __str__(self) -> str:
        return f"{self.run.id} - {self.player.name} (#{self.order})"
