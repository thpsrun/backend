from django.conf import settings
from django.db import models
from django.db.models import Q


class GameAuditEvent(models.Model):
    class EventType(models.TextChoices):
        TIMING_CONFIG_CHANGE = "timing_config_change", "Timing Config Change"
        RECALC_DISPATCH = "recalc_dispatch", "Recalc Dispatch"
        RECALC_BOARD = "recalc_board", "Recalc Board Complete"
        RUN_RECALC = "run_recalc", "Run Recalc"
        SRC_SYNC_ATTEMPT = "src_sync_attempt", "SRC Sync Attempt"
        MODERATOR_ADDED = "moderator_added", "Moderator Added"
        MODERATOR_REMOVED = "moderator_removed", "Moderator Removed"
        APIKEY_REVOKED = "apikey_revoked", "API Key Revoked"

    class ActorKind(models.TextChoices):
        USER = "user", "User"
        API_KEY = "api_key", "API Key"
        SYSTEM = "system", "System"

    game = models.ForeignKey(
        "srl.Games",
        on_delete=models.SET_NULL,
        related_name="audit_events",
        null=True,
        blank=True,
    )
    game_slug_snapshot = models.CharField(
        max_length=255,
        null=True,
        blank=True,
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        db_index=True,
    )
    event_type = models.CharField(
        max_length=32,
        choices=EventType.choices,
    )

    actor_kind = models.CharField(
        max_length=16,
        choices=ActorKind.choices,
        default=ActorKind.SYSTEM,
    )
    actor_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="game_audit_events",
    )
    actor_api_key = models.ForeignKey(
        "api.APIKey",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    actor_label = models.CharField(
        max_length=128,
        blank=True,
        default="",
    )

    target_app = models.CharField(max_length=64, blank=True, default="")
    target_model = models.CharField(max_length=64, blank=True, default="")
    # APIKey rows use a `prefix.hashed_key` PK that fits in 150 charactersso the column must be wide
    # enough to record their pk when they appear as audit targets.
    target_id = models.CharField(max_length=150, blank=True, default="")
    target_repr = models.CharField(max_length=255, blank=True, default="")

    summary = models.CharField(max_length=255)
    payload = models.JSONField(null=True, blank=True)

    class Meta:
        verbose_name = "Game Audit Entry"
        verbose_name_plural = "Game Audit Events"
        ordering = ("-created_at",)
        indexes = [
            models.Index(
                fields=["game", "-created_at"],
                name="audit_game_cr_idx",
            ),
            models.Index(
                fields=["game", "event_type", "-created_at"],
                name="audit_game_type_cr_idx",
            ),
            models.Index(
                fields=["game", "actor_user", "-created_at"],
                name="audit_game_user_cr_idx",
            ),
            models.Index(
                fields=["game", "target_model", "-created_at"],
                name="auditevent_game_target_idx",
            ),
            models.Index(
                fields=["game_slug_snapshot", "-created_at"],
                name="audit_orphan_slug_cr_idx",
                condition=Q(game__isnull=True),
            ),
        ]

    def __str__(
        self,
    ) -> str:
        game_id = self.game.id if self.game else None
        return f"{self.created_at:%Y-%m-%d %H:%M:%S} {self.event_type} game={game_id}"
