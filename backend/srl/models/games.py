from django.conf import settings
from django.db import models
from django.utils.text import slugify

from srl.models.base import LeaderboardChoices
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
            'Default is 250; 25 if this game contains the name "Category '
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

    @property
    def is_ce(self) -> bool:
        return "category extension" in self.name.lower()

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name
