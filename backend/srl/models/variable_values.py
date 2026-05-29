from django.contrib.postgres.fields import ArrayField
from django.db import models
from django.utils.text import slugify

from srl.models.base import LeaderboardChoices, validate_allowed_subset
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
    defaulttime = models.CharField(
        verbose_name="Default Time",
        choices=LeaderboardChoices.choices,
        null=True,
        blank=True,
        default=None,
        help_text=(
            "When not set, the value inherits its variable's timing method (or further up "
            "the chain). When set, this is the most specific override and takes precedence "
            "over the parent variable, the category, and the game. "
            "Precedence: VariableValue > Variable > Category > Game."
        ),
    )
    required_methods = ArrayField(
        base_field=models.CharField(
            max_length=20,
            choices=LeaderboardChoices.choices,
        ),
        null=True,
        blank=True,
        default=None,
        verbose_name="Allowed Timing Methods",
        help_text=(
            "When set, narrows the timing methods allowed for runs with this value. "
            "Must be a non-empty subset of the parent variable's effective allowed methods. "
            "Null inherits from a higher level."
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

    def clean(
        self,
    ) -> None:
        super().clean()
        validate_allowed_subset(
            self,
            parent_allowed=self._resolved_parent_allowed(),
            parent_primary=self._resolved_parent_primary(),
            child_relation_name="",
            child_id_attr="value",
        )

    def _resolved_parent_allowed(
        self,
    ) -> list[str] | None:
        if self.var is None:
            return None
        if self.var.required_methods is not None:
            return list(self.var.required_methods)
        return self.var._resolved_parent_allowed()

    def _resolved_parent_primary(
        self,
    ) -> str | None:
        if self.var is None:
            return None
        if self.var.defaulttime is not None:
            return self.var.defaulttime
        return self.var._resolved_parent_primary()

    def __str__(self):
        if self.var and self.var.game:
            return f"{self.var.game.name}: {self.var.name} - {self.name}"
        return f"(orphaned value) - {self.name}"
