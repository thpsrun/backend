from django.contrib.postgres.fields import ArrayField
from django.db import models

from srl.models.base import LeaderboardChoices, validate_allowed_subset
from srl.models.games import Games


class Categories(models.Model):
    class Meta:
        verbose_name_plural = "Categories"
        ordering = ["name"]
        indexes = [
            models.Index(
                fields=["game", "type"],
                name="idx_categories_game_type",
            ),
            models.Index(
                fields=["appear_on_main"],
                name="idx_categories_main",
            ),
        ]

    class CategoryType(models.TextChoices):
        PER_LEVEL = "per-level", "Individual Level"
        PER_GAME = "per-game", "Full Game"

    id = models.CharField(
        max_length=10,
        primary_key=True,
        verbose_name="Category ID",
    )
    game = models.ForeignKey(
        Games, verbose_name="Linked Game", null=True, on_delete=models.PROTECT
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
    type = models.CharField(
        verbose_name="Type (IL/FG)",
        choices=CategoryType.choices,
    )
    defaulttime = models.CharField(
        verbose_name="Default Time",
        choices=LeaderboardChoices.choices,
        null=True,
        default=None,
        help_text=(
            "When not set, the category's associated game's timing method(s) are used. "
            "When used, the timing method for the ENTIRE category will take take precedence "
            "over what is set for the category's associated game. ALL requests will use this to "
            "determine what timing method is used for the category."
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
            "When set, narrows the timing methods allowed for runs in this category. "
            "Must be a non-empty subset of the parent game's allowed methods. Null inherits "
            "from a higher level."
        ),
    )
    url = models.URLField(
        verbose_name="URL",
    )
    appear_on_main = models.BooleanField(
        verbose_name="Appear on Main Page",
        default=False,
        help_text=(
            "When checked, this category's shortest time will appear on the main page, "
            "regardless of the variables (subcategories)."
        ),
    )
    order = models.IntegerField(
        verbose_name="Sort Order",
        default=0,
        help_text=(
            "Controls display order. order=0 items sort alphabetically as a fallback. "
            "Items with order>=1 sort first in ascending order."
        ),
    )
    players = models.PositiveIntegerField(
        verbose_name="Number of Players",
        default=1,
        help_text="Number of players this category accepts.",
    )
    archive = models.BooleanField(
        verbose_name="Archive Category",
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

    def clean(self) -> None:
        super().clean()
        validate_allowed_subset(
            self,
            parent_allowed=self._parent_allowed(),
            parent_primary=self._inherited_primary(),
            child_relation_name="variables_set",
            child_id_attr="id",
        )

    def _parent_allowed(
        self,
    ) -> list[str] | None:
        if self.game is None:
            return None
        return (
            self.game.required_methods_il
            if self.type == self.CategoryType.PER_LEVEL
            else self.game.required_methods_fg
        )

    def _inherited_primary(
        self,
    ) -> str | None:
        if self.game is None:
            return None
        return (
            self.game.idefaulttime
            if self.type == self.CategoryType.PER_LEVEL
            else self.game.defaulttime
        )

    def __str__(self):
        return self.name
