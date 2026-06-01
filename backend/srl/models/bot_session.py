from django.db import models

from srl.encryption import decrypt_src_key, encrypt_src_key


class BotSession(models.Model):
    class Meta:
        verbose_name = "Bot Session"
        verbose_name_plural = "Bot Session"

    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        EXPIRED = "expired", "Expired"
        REFRESHING = "refreshing", "Refreshing"
        LOCKED_OUT = "locked_out", "Locked Out"

    phpsessid_encrypted = models.TextField(
        blank=True,
        default="",
    )
    csrf_token = models.CharField(
        max_length=64,
        blank=True,
        default="",
    )
    validated_at = models.DateTimeField(
        null=True,
        blank=True,
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.EXPIRED,
    )
    last_refresh_attempt_at = models.DateTimeField(
        null=True,
        blank=True,
    )
    v2_enabled_override = models.BooleanField(
        null=True,
        blank=True,
        default=None,
        help_text=(
            "Runtime override for SRC_V2_ENABLED. " "None inherits the env value."
        ),
    )
    consecutive_refresh_failures = models.PositiveSmallIntegerField(
        default=0,
        help_text=(
            "Counter of refresh_bot_session() failures since last "
            "successful refresh. Used to trip the circuit breaker "
            "at >= 3."
        ),
    )
    disabled_by_circuit_breaker = models.BooleanField(
        default=False,
        help_text=(
            "True when v2 was auto-disabled by trip_circuit_breaker(). "
            "Distinguishes 'admin paused' from 'system tripped'."
        ),
    )
    last_severe_error_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Timestamp of most recent breaker trip.",
    )
    last_severe_error_category = models.CharField(
        max_length=20,
        blank=True,
        default="",
        help_text="ErrorCategory value of most recent breaker trip.",
    )

    @classmethod
    def load(
        cls,
    ) -> "BotSession":
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj

    def set_phpsessid(
        self,
        plain: str,
    ) -> None:
        self.phpsessid_encrypted = encrypt_src_key(plain) if plain else ""

    def get_phpsessid(
        self,
    ) -> str:
        if not self.phpsessid_encrypted:
            return ""
        return decrypt_src_key(self.phpsessid_encrypted)

    def __str__(
        self,
    ) -> str:
        return f"BotSession[{self.status}] validated_at={self.validated_at}"
