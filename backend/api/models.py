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


class APIKeyManager(BaseAPIKeyManager):
    def get_usable_keys(
        self,
    ) -> models.QuerySet:
        # BaseAPIKeyManager only filters revoked=False. For this project's
        # "usable" semantics we also require the owning user active and the
        # key not past its expiry_date.
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
        """Mark this key as revoked with a reason and timestamp. Idempotent:
        returns False if the key was already revoked, True if this call did it.
        """
        if self.revoked:
            return False
        self.revoked = True
        self.revoked_reason = reason
        self.revoked_at = timezone.now()
        self.save(update_fields=["revoked", "revoked_reason", "revoked_at"])
        return True
