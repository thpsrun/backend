from typing import Any

from django.conf import settings
from django.contrib.postgres.fields import ArrayField
from django.db import models
from django.db.models import Q
from django.utils import timezone
from rest_framework_api_key.models import AbstractAPIKey, BaseAPIKeyManager


class APIKeyRevokedReason(models.TextChoices):
    NONE = "", "Not revoked"
    USER = "user", "Revoked by owner"
    PERMISSION_REVOKED = "permission_revoked", "Permission revoked"
    ADMIN = "admin", "Revoked by admin"
    BANNED = "banned", "Banned by admin"


class APIActivityAuthMethod(models.TextChoices):
    API_KEY = "api_key", "API Key"
    SESSION = "session", "Session"
    ANONYMOUS = "anonymous", "Anonymous"


class APIActivityAction(models.TextChoices):
    CREATE = "create", "Create"
    UPDATE = "update", "Update"
    DELETE = "delete", "Delete"
    READ = "read", "Read"
    OTHER = "other", "Other"


class APIKeyManager(BaseAPIKeyManager):
    def get_usable_keys(
        self,
    ) -> models.QuerySet:
        return (
            super()
            .get_usable_keys()
            .filter(user__is_active=True)
            .filter(
                Q(expiry_date__isnull=True) | Q(expiry_date__gt=timezone.now()),
            )
        )

    def create_key(
        self,
        **kwargs: Any,
    ) -> tuple["APIKey", str]:
        # AbstractAPIKey.name is NOT NULL; default it from label so callers
        # only have to provide the user-facing label.
        if "name" not in kwargs and "label" in kwargs:
            kwargs["name"] = str(kwargs["label"])[:50]
        return super().create_key(**kwargs)  # type: ignore

    def get_from_key(
        self,
        key: str,
    ) -> "APIKey":
        return super().get_from_key(key)  # type: ignore


class APIKey(AbstractAPIKey):
    objects: APIKeyManager = APIKeyManager()

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="api_keys",
    )
    label = models.CharField(max_length=100)
    description = models.TextField(blank=True, default="")
    scope_games = models.ManyToManyField(
        "srl.Games",
        blank=True,
        related_name="scoping_keys",
    )
    scope_capabilities = ArrayField(
        base_field=models.CharField(max_length=64),
        default=list,
        blank=True,
    )
    last_used = models.DateTimeField(null=True, blank=True)
    last_used_ip = models.GenericIPAddressField(null=True, blank=True)
    revoked_reason = models.CharField(
        max_length=32,
        blank=True,
        default="",
        choices=APIKeyRevokedReason.choices,
    )
    revoked_at = models.DateTimeField(null=True, blank=True, db_index=True)

    class Meta(AbstractAPIKey.Meta):
        indexes = [
            models.Index(fields=["user"]),
            models.Index(fields=["last_used"]),
        ]
        verbose_name = "API Key"
        verbose_name_plural = "API Keys"

    def __str__(
        self,
    ) -> str:
        return f"{self.label} ({self.user})"

    def revoke(
        self,
        reason: "APIKeyRevokedReason | str",
    ) -> bool:
        """Mark this key as revoked with a reason and timestamp."""
        if self.revoked:
            return False
        self.revoked = True
        self.revoked_reason = reason
        self.revoked_at = timezone.now()
        self.save(update_fields=["revoked", "revoked_reason", "revoked_at"])
        return True


class APIActivityLog(models.Model):
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="api_activity",
    )
    api_key = models.ForeignKey(
        "api.APIKey",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="activity",
    )
    auth_method = models.CharField(
        max_length=16,
        choices=APIActivityAuthMethod.choices,
        default=APIActivityAuthMethod.ANONYMOUS,
    )

    key_label_snapshot = models.CharField(max_length=100, blank=True, default="")
    method = models.CharField(max_length=8)
    path = models.CharField(max_length=512)
    action = models.CharField(
        max_length=16,
        choices=APIActivityAction.choices,
        default=APIActivityAction.OTHER,
    )
    status_code = models.PositiveSmallIntegerField()
    ip = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=255, blank=True, default="")
    target_app = models.CharField(max_length=64, blank=True, default="")
    target_model = models.CharField(max_length=64, blank=True, default="")
    target_id = models.CharField(max_length=64, blank=True, default="")
    target_repr = models.CharField(max_length=255, blank=True, default="")
    change_summary = models.JSONField(null=True, blank=True)

    class Meta:
        verbose_name = "API Activity Entry"
        verbose_name_plural = "API Activity"
        ordering = ("-created_at",)
        indexes = [
            models.Index(fields=["user", "-created_at"], name="api_actl_user_cr_idx"),
            models.Index(fields=["api_key", "-created_at"], name="api_actl_key_cr_idx"),
            models.Index(
                fields=["target_app", "target_model", "target_id"],
                name="api_actl_target_idx",
            ),
            models.Index(fields=["status_code"], name="api_actl_status_idx"),
            models.Index(fields=["method"], name="api_actl_method_idx"),
            models.Index(
                fields=["-created_at"],
                name="apiactivitylog_created_idx",
            ),
            models.Index(
                fields=["target_app", "target_model", "-created_at"],
                name="apiactivitylog_target_idx",
            ),
        ]

    def __str__(
        self,
    ) -> str:
        who = self.user.id if self.user else self.api_key.id if self.api_key else "anon"
        return f"{self.created_at:%Y-%m-%d %H:%M:%S} {self.method} {self.path} ({who})"
