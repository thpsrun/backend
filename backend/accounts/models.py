import uuid

from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.db import models
from django_resized import ResizedImageField
from srl.models.base import validate_profile_bg


class CustomUser(AbstractUser):
    class Meta:
        verbose_name = "User"
        verbose_name_plural = "Users"

    encrypted_api_key = models.TextField(
        verbose_name="Encrypted SRC API Key",
        null=True,
        blank=True,
        help_text="Fernet-encrypted Speedrun.com API key. Never expose in API responses.",
    )
    bio = models.TextField(
        verbose_name="Biography",
        max_length=1000,
        null=True,
        blank=True,
        help_text="Markdown-formatted biography. Max 1000 characters.",
    )
    therun_gg = models.TextField(
        verbose_name="therun.gg Profile",
        max_length=30,
        null=True,
        blank=True,
        help_text="therun.gg account.",
    )
    short_bio = models.CharField(
        verbose_name="Short Bio",
        max_length=100,
        null=True,
        blank=True,
        help_text="Brief bio displayed on profile. Max 100 characters. Emojis allowed.",
    )

    gradient_1 = models.CharField(
        verbose_name="Gradient Color 1",
        max_length=7,
        null=True,
        blank=True,
        help_text="Hex color for name gradient (#RRGGBB). Primary/solid color.",
    )
    gradient_2 = models.CharField(
        verbose_name="Gradient Color 2",
        max_length=7,
        null=True,
        blank=True,
        help_text="Hex color for name gradient (#RRGGBB). Requires gradient_1.",
    )
    gradient_3 = models.CharField(
        verbose_name="Gradient Color 3",
        max_length=7,
        null=True,
        blank=True,
        help_text="Hex color for name gradient (#RRGGBB). Requires gradient_2.",
    )
    profile_bg = ResizedImageField(
        size=[2560, 1440],
        upload_to="profile_bg",
        verbose_name="Profile Background",
        validators=[validate_profile_bg],
        null=True,
        blank=True,
        help_text="Profile background image. Max 2560x1440. Max 10MB.",
    )


class UserDataExport(models.Model):
    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending"
        RUNNING = "RUNNING", "Running"
        READY = "READY", "Ready"
        FAILED = "FAILED", "Failed"
        EXPIRED = "EXPIRED", "Expired"

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="data_exports",
    )
    status = models.CharField(
        max_length=16,
        choices=Status.choices,
        default=Status.PENDING,
        db_index=True,
    )
    requested_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    file_path = models.CharField(max_length=512, blank=True)
    file_size_bytes = models.BigIntegerField(null=True, blank=True)
    error_message = models.TextField(blank=True)

    class Meta:
        indexes = [
            models.Index(fields=["user", "requested_at"]),
            models.Index(fields=["user", "status"]),
        ]
        ordering = ["-requested_at"]
