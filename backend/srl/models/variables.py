from django.core.exceptions import ValidationError
from django.db import models
from django.utils.text import slugify

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

    type_choices = [
        ("global", "Entire Game"),
        ("full-game", "Only Full Game Runs"),
        ("all-levels", "Only IL Runs"),
        ("single-level", "Specific IL"),
    ]

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
        choices=type_choices,
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

    def __str__(self):
        return self.name
