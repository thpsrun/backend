from typing import Any

from django.db import models
from rest_framework_api_key.models import AbstractAPIKey


class RoleAPIKey(AbstractAPIKey):
    class Role(models.TextChoices):
        READ_ONLY = "read_only", "Read Only"
        CONTRIBUTOR = "contributor", "Contributor"
        MODERATOR = "moderator", "Moderator"
        ADMIN = "admin", "Admin"

    role = models.CharField(
        max_length=20,
        choices=Role.choices,
        default=Role.READ_ONLY,
        help_text="Permission level for this API key",
    )

    description = models.TextField(
        blank=True,
        help_text="Optional description of what this key is used for",
    )

    created_by = models.CharField(
        max_length=100,
        blank=True,
        help_text="Who created this API key",
    )

    last_used = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Last time this key was used",
    )

    class Meta:
        verbose_name = "Role API Key"
        verbose_name_plural = "Role API Keys"
        ordering = ["-created"]

    def __str__(self) -> str:
        return f"{self.name} ({self.role})"

    @property
    def role_display(self) -> str:
        """Get human-readable role name."""
        return self.get_role_display()

    def has_role(
        self,
        required_role: str,
    ) -> bool:
        """Check if this API key has sufficient role permissions.

        Arguments:
            required_role (str): Minimum required role
        """
        role_hierarchy: dict[str, int] = {
            "read_only": 1,
            "contributor": 2,
            "moderator": 3,
            "admin": 4,
        }

        user_level = role_hierarchy.get(self.role, 0)
        required_level = role_hierarchy.get(required_role, 0)

        return user_level >= required_level

    def save(
        self,
        *args: Any,
        **kwargs: Any,
    ) -> None:
        super().save(*args, **kwargs)
