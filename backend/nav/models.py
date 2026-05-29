from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models


class NavItem(models.Model):
    class Meta:
        verbose_name = "Nav Item"
        verbose_name_plural = "Nav Items"
        ordering = ["order", "name"]

    name = models.CharField(
        max_length=100,
        verbose_name="Display Label",
    )
    url = models.CharField(
        max_length=255,
        verbose_name="URL",
        blank=True,
        null=True,
        help_text="Optional link target. Leave blank for group headers.",
    )
    parent = models.ForeignKey(
        "self",
        verbose_name="Parent Item",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="children",
    )
    order = models.IntegerField(
        verbose_name="Sort Order",
        default=0,
        help_text=(
            "Controls display order. order=0 items sort alphabetically as a fallback. "
            "Items with order>=1 sort first in ascending order."
        ),
    )
    is_visible = models.BooleanField(
        verbose_name="Visible",
        default=True,
    )
    updated_at = models.DateTimeField(
        auto_now=True,
    )

    def clean(
        self,
    ) -> None:
        """Enforce the configured maximum nesting depth by walking the parent chain."""
        super().clean()
        max_depth = settings.NAVBAR_MAX_DEPTH
        depth = 1
        current = self.parent
        while current is not None:
            depth += 1
            if depth > max_depth:
                raise ValidationError(
                    f"Navigation items cannot be nested more than {max_depth} levels deep."
                )
            current = current.parent

    def __str__(
        self,
    ) -> str:
        return self.name


class SocialLink(models.Model):
    class Meta:
        verbose_name = "Social Link"
        verbose_name_plural = "Social Links"
        ordering = ["order", "platform"]

    platform = models.CharField(
        max_length=50,
        verbose_name="Platform",
        help_text='e.g. "Discord", "Twitter", "YouTube"',
    )
    url = models.URLField(
        verbose_name="URL",
    )
    order = models.IntegerField(
        verbose_name="Sort Order",
        default=0,
        help_text=(
            "Controls display order. order=0 items sort alphabetically as a fallback. "
            "Items with order>=1 sort first in ascending order."
        ),
    )
    is_visible = models.BooleanField(
        verbose_name="Visible",
        default=True,
    )
    updated_at = models.DateTimeField(
        auto_now=True,
    )

    def __str__(
        self,
    ) -> str:
        return self.platform
