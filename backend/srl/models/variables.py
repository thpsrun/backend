from django.contrib.postgres.fields import ArrayField
from django.core.exceptions import ValidationError
from django.db import models
from django.utils.text import slugify

from srl.models.base import LeaderboardChoices
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
    allowed_methods = ArrayField(
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

        errors: dict = {}
        parent_allowed = self._resolved_parent_allowed()
        parent_primary = self._resolved_parent_primary()

        if self.allowed_methods is not None:
            if len(self.allowed_methods) == 0:
                errors["allowed_methods"] = (
                    "Cannot be an empty list; use null to inherit."
                )
            elif parent_allowed is not None and not set(self.allowed_methods) <= set(
                parent_allowed
            ):
                errors["allowed_methods"] = (
                    f"Must be a subset of the parent's allowed methods "
                    f"({list(parent_allowed)})."
                )
            elif (
                self.defaulttime is None
                and parent_primary is not None
                and parent_primary not in self.allowed_methods
            ):
                errors["defaulttime"] = (
                    f"Inherited primary ({parent_primary}) is not in the narrowed "
                    f"allowed_methods; set defaulttime explicitly."
                )

        if self.defaulttime is not None:
            effective_allowed = self.allowed_methods or parent_allowed
            if (
                effective_allowed is not None
                and self.defaulttime not in effective_allowed
            ):
                errors["defaulttime"] = (
                    f"defaulttime ({self.defaulttime}) must be one of allowed_methods "
                    f"({list(effective_allowed)})."
                )

        if self.pk and self.allowed_methods is not None:
            allowed_set = set(self.allowed_methods)
            bad_vals = self.variablevalues_set.filter(allowed_methods__isnull=False)  # type: ignore
            offenders = [
                vv.value
                for vv in bad_vals
                if not set(vv.allowed_methods).issubset(allowed_set)
            ]
            if offenders:
                errors["allowed_methods"] = (
                    f"Cannot narrow: variable values rely on removed methods. "
                    f"Offending value ids: {offenders}"
                )

        if errors:
            raise ValidationError(errors)

    def _resolved_parent_allowed(
        self,
    ) -> list[str] | None:
        if self.cat is not None and self.cat.allowed_methods is not None:
            return list(self.cat.allowed_methods)
        if self.game is None:
            return None
        if self.cat is not None:
            return list(
                self.game.allowed_methods_il
                if self.cat.type == "per-level"
                else self.game.allowed_methods_fg
            )
        is_il = self.scope in ("all-levels", "single-level")
        return list(
            self.game.allowed_methods_il if is_il else self.game.allowed_methods_fg
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
