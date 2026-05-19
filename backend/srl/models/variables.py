from django.contrib.postgres.fields import ArrayField
from django.core.exceptions import ValidationError
from django.db import models
from django.utils.text import slugify

from srl.models.base import LeaderboardChoices, validate_allowed_subset
from srl.models.categories import Categories
from srl.models.games import Games
from srl.models.levels import Levels


class Variables(models.Model):
    class Meta:
        verbose_name_plural = "Variables"
        indexes = [
            models.Index(
                fields=["game", "cat"],
                name="idx_variables_game_cat",
            ),
            models.Index(
                fields=["game", "scope"],
                name="idx_variables_game_scope",
            ),
        ]

    class VariableScope(models.TextChoices):
        GLOBAL = "global", "Entire Game"
        FULL_GAME = "full-game", "Only Full Game Runs"
        ALL_LEVELS = "all-levels", "Only IL Runs"
        SINGLE_LEVEL = "single-level", "Specific IL"

    id = models.CharField(
        max_length=10,
        primary_key=True,
        verbose_name="Variable ID",
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
    game = models.ForeignKey(
        Games,
        verbose_name="Linked Game",
        null=True,
        on_delete=models.PROTECT,
    )
    cat = models.ForeignKey(
        Categories,
        verbose_name="Category",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        help_text=(
            'If not set, the variable  is seen as a "global" variable for the scope you choose '
            'below. For example: a "global" variable set for "Only IL Runs" will make it a GLOBAL '
            "variable for IL speedruns."
        ),
    )
    scope = models.CharField(
        verbose_name="Scope (FG/IL)",
        choices=VariableScope.choices,
    )
    defaulttime = models.CharField(
        verbose_name="Default Time",
        choices=LeaderboardChoices.choices,
        null=True,
        blank=True,
        default=None,
        help_text=(
            "When not set, the variable inherits its category's timing method (or the game's "
            "if the category does not set one). When set, this takes precedence over both the "
            "category and game timing for any run that includes this variable. "
            "Precedence: Variable > Category > Game."
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
            "When set, narrows the timing methods allowed for runs that include this "
            "variable. Must be a non-empty subset of the parent (category/game). Null "
            "inherits from a higher level."
        ),
    )
    level = models.ForeignKey(
        Levels,
        verbose_name="Associated Level",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        help_text=(
            'If "scope" is set to "single-level", then a level must be associated. Otherwise, '
            "keep null."
        ),
    )
    archive = models.BooleanField(
        verbose_name="Archive Variable",
        default=False,
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

    def clean(self):
        if (self.level is None) and (self.scope == "single-level"):
            raise ValidationError(
                'If "scope" is set to "single-level", a level must be specified.'
            )
        elif (self.level) and (self.scope != "single-level"):
            raise ValidationError(
                'If a "level" is set, then "scope" must be set to "single-level".'
            )

        validate_allowed_subset(
            self,
            parent_allowed=self._resolved_parent_allowed(),
            parent_primary=self._resolved_parent_primary(),
            child_relation_name="variablevalues_set",
            child_id_attr="value",
        )

    def _resolved_parent_allowed(
        self,
    ) -> list[str] | None:
        if self.cat is not None and self.cat.required_methods is not None:
            return list(self.cat.required_methods)
        if self.game is None:
            return None
        if self.cat is not None:
            return list(
                self.game.required_methods_il
                if self.cat.type == "per-level"
                else self.game.required_methods_fg
            )
        is_il = self.scope in ("all-levels", "single-level")
        return list(
            self.game.required_methods_il if is_il else self.game.required_methods_fg
        )

    def _resolved_parent_primary(
        self,
    ) -> str | None:
        if self.cat is not None and self.cat.defaulttime is not None:
            return self.cat.defaulttime
        if self.game is None:
            return None
        if self.cat is not None:
            return (
                self.game.idefaulttime
                if self.cat.type == "per-level"
                else self.game.defaulttime
            )
        is_il = self.scope in ("all-levels", "single-level")
        return self.game.idefaulttime if is_il else self.game.defaulttime

    def __str__(self):
        return self.name
