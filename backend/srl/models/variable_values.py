from django.db import models
from django.utils.text import slugify

from srl.models.variables import Variables


class VariableValues(models.Model):
    class Meta:
        verbose_name_plural = "Variable Values"
        ordering = ["var__game", "var", "var__scope", "name"]

    var = models.ForeignKey(
        Variables,
        verbose_name="Linked Variable",
        null=True,
        on_delete=models.PROTECT,
    )
    name = models.CharField(
        max_length=50,
        verbose_name="Name",
    )
    slug = models.SlugField(
        max_length=50,
        verbose_name="Slug",
        blank=True,
    )
    value = models.CharField(
        max_length=10,
        primary_key=True,
        verbose_name="Value ID",
    )
    appear_on_main = models.BooleanField(
        verbose_name="Appear on Main Page",
        default=False,
        help_text=(
            "When unchecked, runs with this variable value will NOT appear "
            "on the main page, even if the parent category is enabled."
        ),
    )
    order = models.IntegerField(
        verbose_name="Sort Order",
        default=0,
        help_text=(
            "Controls display order within this variable's values. "
            "order=0 items sort alphabetically as a fallback. "
            "Items with order>=1 sort first in ascending order."
        ),
    )
    archive = models.BooleanField(
        verbose_name="Archive Value",
        default=False,
    )
    rules = models.TextField(
        max_length=5000,
        verbose_name="Rules",
        blank=True,
        null=True,
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
    )
    updated_at = models.DateTimeField(
        auto_now=True,
    )

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)

    def __str__(self):
        if self.var and self.var.game:
            return f"{self.var.game.name}: {self.var.name} - {self.name}"
        return f"(orphaned runff) - {self.name}"
