from django.conf import settings
from django.db import models


class Notification(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="notifications",
    )
    type = models.CharField(max_length=50, db_index=True)

    target_type = models.CharField(max_length=50, blank=True, default="")
    target_id = models.CharField(max_length=100, blank=True, default="")

    title = models.CharField(max_length=255)
    body = models.TextField(blank=True, default="")
    payload = models.JSONField(default=dict, blank=True)

    is_read = models.BooleanField(default=False)
    read_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ("-created_at",)
        indexes = [
            models.Index(
                fields=["user", "is_read", "-created_at"],
                name="notif_user_read_cr_idx",
            ),
            models.Index(
                fields=["user", "target_type", "target_id"],
                name="notif_user_target_idx",
            ),
            models.Index(
                fields=["user", "type", "target_id"],
                name="notif_user_type_target_idx",
            ),
        ]

    def __str__(self) -> str:
        return f"[{self.type}] {self.title} -> {self.user.id}"


class NotificationPreference(models.Model):
    CHANNEL_IN_APP = "in_app"
    CHANNEL_EMAIL = "email"
    CHANNEL_CHOICES = (
        (CHANNEL_IN_APP, "In-app"),
        (CHANNEL_EMAIL, "Email"),
    )

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="notification_prefs",
    )
    type = models.CharField(max_length=50)
    channel = models.CharField(
        max_length=20,
        choices=CHANNEL_CHOICES,
        default=CHANNEL_IN_APP,
    )
    enabled = models.BooleanField(default=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["user", "type", "channel"],
                name="uniq_notif_pref_user_type_channel",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.user.id}/{self.type}/{self.channel}={self.enabled}"
