from django.conf import settings
from django.contrib.postgres.fields import ArrayField
from django.core.exceptions import ValidationError
from django.db import models
from django.utils.text import slugify

from srl.models.base import LeaderboardChoices, all_methods_default
from srl.models.platforms import Platforms
from srl.models.players import Players


class Games(models.Model):
    class Meta:
        verbose_name_plural = "Games"
        ordering = ["release"]

    id = models.CharField(
        max_length=10,
        primary_key=True,
        verbose_name="SRL Game ID",
    )
    name = models.CharField(
        max_length=55,
        verbose_name="Name",
    )
    slug = models.SlugField(
        max_length=20,
        verbose_name="Abbreviation/Slug",
        unique=True,
    )
    twitch = models.CharField(
        max_length=55,
        verbose_name="Twitch Name",
        null=True,
        blank=True,
    )
    release = models.DateField(
        verbose_name="Release Date",
    )
    boxart = models.URLField(
        verbose_name="Box Art URL",
    )
    defaulttime = models.CharField(
        verbose_name="Default Time",
        choices=LeaderboardChoices.choices,
        default=LeaderboardChoices.REALTIME,
    )
    idefaulttime = models.CharField(
        verbose_name="ILs Default Time",
        choices=LeaderboardChoices.choices,
        default=LeaderboardChoices.REALTIME,
        help_text=(
            "Sometimes leaderboards have one timing standard for full game "
            "speedruns and another standard for ILs. This setting lets you change the "
            "game-specific IL timing method.<br />NOTE: This defaults to RTA upon a game "
            "being created and must be set manually."
        ),
    )
    required_methods_fg = ArrayField(
        base_field=models.CharField(
            max_length=20,
            choices=LeaderboardChoices.choices,
        ),
        default=all_methods_default,
        blank=False,
        verbose_name="Allowed FG Timing Methods",
        help_text=(
            "Timing methods allowed for full-game runs of this game. Must include "
            "defaulttime."
        ),
    )
    required_methods_il = ArrayField(
        base_field=models.CharField(
            max_length=20,
            choices=LeaderboardChoices.choices,
        ),
        default=all_methods_default,
        blank=False,
        verbose_name="Allowed IL Timing Methods",
        help_text=(
            "Timing methods allowed for individual-level runs of this game. Must include "
            "idefaulttime."
        ),
    )
    platforms = models.ManyToManyField(
        Platforms,
        verbose_name="Platforms",
    )
    moderators = models.ManyToManyField(
        Players,
        related_name="moderated_games",
        verbose_name="Moderators",
        blank=True,
        help_text=(
            "Players who are moderators for this game on thps.run. "
            "If a player is a moderator here but not on SRC, thps.run takes precedence."
        ),
    )
    pointsmax = models.PositiveSmallIntegerField(
        verbose_name="Full Game WR Point Maximum",
        default=settings.POINTS_MAX_FG,
        help_text=(
            'Default is 1000; 25 if this game contains the name "Category '
            'Extension". This is the maximum total of points a full-game speedrun '
            "receives if it is the world record. All lower-ranked speedruns recieve less "
            "based upon an algorithmic formula.<br />NOTE: Changing this value will ONLY "
            "affect new runs. If you change this value, you will need to reset runs for "
            "this game from the admin panel."
        ),
    )
    ipointsmax = models.PositiveSmallIntegerField(
        verbose_name="IL WR Point Maximum",
        default=settings.POINTS_MAX_CE,
        help_text=(
            'Default is 250; 25LO if this game contains the name "Category '
            'Extension". This is the maximum total of points an IL speedrun receives if '
            "it is the world record. All lower-ranked speedruns recieve less based upon an "
            "algorithmic formula.<br />NOTE: Changing this value will ONLY affect new "
            "runs. If you change this value, you will need to reset runs for this game "
            "from the admin panel."
        ),
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
    verbose_recalc_log = models.BooleanField(
        verbose_name="Verbose Recalc Logging",
        default=False,
        help_text=(
            "When enabled, every per-board recalculation writes a `RECALC_BOARD` entry "
            "to this game's audit log. Off by default."
        ),
    )

    @property
    def is_ce(
        self,
    ) -> bool:
        return "category extension" in self.name.lower()

    def clean(self) -> None:
        super().clean()
        errors: dict = {}
        if not self.required_methods_fg:
            errors["required_methods_fg"] = "Must contain at least one timing method."
        if not self.required_methods_il:
            errors["required_methods_il"] = "Must contain at least one timing method."
        if (
            self.required_methods_fg
            and self.defaulttime not in self.required_methods_fg
        ):
            errors["defaulttime"] = (
                f"defaulttime ({self.defaulttime}) must be one of required_methods_fg "
                f"({list(self.required_methods_fg)})."
            )
        if (
            self.required_methods_il
            and self.idefaulttime not in self.required_methods_il
        ):
            errors["idefaulttime"] = (
                f"idefaulttime ({self.idefaulttime}) must be one of required_methods_il "
                f"({list(self.required_methods_il)})."
            )
        if self.pk and self.required_methods_fg:
            fg_set = set(self.required_methods_fg)
            bad_cats = self.categories_set.filter(  # type: ignore
                type="per-game",
                required_methods__isnull=False,
            )
            offenders = [
                c.id for c in bad_cats if not set(c.required_methods).issubset(fg_set)
            ]
            if offenders:
                errors["required_methods_fg"] = (
                    f"Cannot narrow: per-game categories rely on removed methods. "
                    f"Offending category ids: {offenders}"
                )

            # Reject narrowing if a per-game category's `defaulttime` would land outside
            # the new window. Categories that inherit `defaulttime` are checked against
            # the new game `defaulttime`, which is already constrained above.
            default_offenders = [
                c.id
                for c in self.categories_set.filter(  # type: ignore
                    type="per-game",
                    defaulttime__isnull=False,
                )
                if c.defaulttime not in fg_set
            ]
            if default_offenders:
                msg = (
                    f"Cannot narrow: per-game categories have defaulttime outside the "
                    f"new window. Offending category ids: {default_offenders}"
                )
                existing = errors.get("required_methods_fg")
                errors["required_methods_fg"] = f"{existing} {msg}" if existing else msg

        if self.pk and self.required_methods_il:
            il_set = set(self.required_methods_il)
            bad_cats = self.categories_set.filter(  # type: ignore
                type="per-level",
                required_methods__isnull=False,
            )
            offenders = [
                c.id for c in bad_cats if not set(c.required_methods).issubset(il_set)
            ]
            if offenders:
                errors["required_methods_il"] = (
                    f"Cannot narrow: per-level categories rely on removed methods. "
                    f"Offending category ids: {offenders}"
                )

            default_offenders = [
                c.id
                for c in self.categories_set.filter(  # type: ignore
                    type="per-level",
                    defaulttime__isnull=False,
                )
                if c.defaulttime not in il_set
            ]
            if default_offenders:
                msg = (
                    f"Cannot narrow: per-level categories have defaulttime outside the "
                    f"new window. Offending category ids: {default_offenders}"
                )
                existing = errors.get("required_methods_il")
                errors["required_methods_il"] = f"{existing} {msg}" if existing else msg

        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name
