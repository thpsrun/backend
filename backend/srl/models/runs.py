from django.db import models

from srl.models.categories import Categories
from srl.models.games import Games
from srl.models.levels import Levels
from srl.models.platforms import Platforms
from srl.models.players import Players
from srl.models.variable_values import VariableValues
from srl.models.variables import Variables


class Runs(models.Model):
    class Meta:
        verbose_name_plural = "Runs"
        indexes = [
            models.Index(
                fields=["game", "category", "place"],
                name="idx_runs_game_cat_place",
            ),
            models.Index(
                fields=["game", "level", "place"],
                name="idx_runs_game_level_place",
            ),
            models.Index(
                fields=["place", "obsolete", "vid_status"],
                name="idx_runs_place_obs_status",
            ),
            models.Index(
                fields=["game", "category", "level"],
                name="idx_runs_game_cat_level",
            ),
            models.Index(
                fields=["-v_date"],
                name="idx_runs_vdate_desc",
            ),
            models.Index(
                fields=["runtype"],
                name="idx_runs_runtype",
            ),
        ]

    statuschoices = [
        ("verified", "Verified"),
        ("new", "Unverified"),
        ("rejected", "Rejected"),
    ]

    runtype = [
        ("main", "Full Game"),
        ("il", "Individual Level"),
    ]

    id = models.CharField(
        max_length=10,
        primary_key=True,
        verbose_name="Run ID",
    )
    runtype = models.CharField(
        max_length=5,
        choices=runtype,
        verbose_name="Full-Game or IL",
    )
    game = models.ForeignKey(
        Games,
        verbose_name="Game",
        on_delete=models.CASCADE,
    )
    category = models.ForeignKey(
        Categories,
        verbose_name="Category",
        blank=True,
        null=True,
        on_delete=models.SET_NULL,
    )
    level = models.ForeignKey(
        Levels,
        verbose_name="Level",
        blank=True,
        null=True,
        on_delete=models.SET_NULL,
    )
    variables = models.ManyToManyField(
        Variables,
        verbose_name="Variables",
        through="RunVariableValues",
        related_name="runs",
    )
    players = models.ManyToManyField(
        Players,
        verbose_name="Players",
        through="RunPlayers",
        related_name="runs",
        blank=True,
        help_text=(
            "Players who participated in this run. If no players are specified, "
            "the run will be displayed as Anonymous."
        ),
    )
    place = models.PositiveSmallIntegerField(
        verbose_name="Placing",
    )
    url = models.URLField(
        verbose_name="URL",
    )
    video = models.URLField(
        verbose_name="Video",
        blank=True,
        null=True,
    )
    date = models.DateTimeField(
        verbose_name="Submitted Date",
        blank=True,
        null=True,
    )
    v_date = models.DateTimeField(
        verbose_name="Verified Date",
        blank=True,
        null=True,
    )
    time = models.CharField(
        max_length=25,
        verbose_name="RTA Time",
        blank=True,
        null=True,
    )
    time_secs = models.FloatField(
        verbose_name="RTA Time (Seconds)",
        blank=True,
        null=True,
    )
    timenl = models.CharField(
        max_length=25,
        verbose_name="LRT Time",
        blank=True,
        null=True,
    )
    timenl_secs = models.FloatField(
        verbose_name="LRT Time (Seconds)",
        blank=True,
        null=True,
    )
    timeigt = models.CharField(
        max_length=25,
        verbose_name="IGT Time",
        blank=True,
        null=True,
    )
    timeigt_secs = models.FloatField(
        verbose_name="IGT Time (Seconds)",
        blank=True,
        null=True,
    )
    points = models.PositiveSmallIntegerField(
        verbose_name="Packle Points",
        default=0,
    )
    bonus = models.PositiveSmallIntegerField(
        verbose_name="Streak Bonus",
        default=0,
        help_text="Usually used to count the number of months (up to 4) a run has been the record.",
    )
    platform = models.ForeignKey(
        Platforms,
        verbose_name="Platform",
        blank=True,
        null=True,
        on_delete=models.SET_NULL,
    )
    emulated = models.BooleanField(
        verbose_name="Emulated?",
        default=False,
    )
    vid_status = models.CharField(
        verbose_name="SRC Status",
        choices=statuschoices,
        default="verified",
        help_text=(
            "This is the current status of the run, according to Speedrun.com. "
            'It should be updated whenever the run is approved. Runs set as "Unverified" '
            'or "Rejected" do not appear anywhere on this site.'
        ),
    )
    approver = models.ForeignKey(
        Players,
        verbose_name="Approver",
        blank=True,
        null=True,
        on_delete=models.SET_NULL,
        related_name="approver",
    )
    obsolete = models.BooleanField(
        verbose_name="Obsolete?",
        default=False,
        help_text=(
            "When True, the run will be considered obsolete. Points will not "
            "count towards the player's total."
        ),
    )
    arch_video = models.URLField(
        verbose_name="Archived Video URL",
        blank=True,
        null=True,
        help_text=(
            "Optional field. If you have a mirrored link to a video, you can "
            "input it here."
        ),
    )
    description = models.TextField(
        max_length=5000,
        verbose_name="Description",
        blank=True,
        null=True,
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
    )
    updated_at = models.DateTimeField(
        auto_now=True,
    )

    # Maps timing method -> (display string field, seconds field)
    _TIMING_FIELD_MAP: dict[str, tuple[str, str]] = {
        "realtime": ("time", "time_secs"),
        "realtime_noloads": ("timenl", "timenl_secs"),
        "ingame": ("timeigt", "timeigt_secs"),
    }

    def _primary_timing_method(
        self,
    ) -> str:
        # Category timing overrides game defaults; IL runs use idefaulttime
        if self.category and self.category.defaulttime:
            return self.category.defaulttime
        if self.runtype == "il":
            return self.game.idefaulttime
        return self.game.defaulttime

    @property
    def p_time(
        self,
    ) -> str | None:
        method = self._primary_timing_method()
        field, _ = self._TIMING_FIELD_MAP[method]
        return getattr(self, field)

    @property
    def p_time_secs(
        self,
    ) -> float | None:
        method = self._primary_timing_method()
        _, secs_field = self._TIMING_FIELD_MAP[method]
        return getattr(self, secs_field)

    def __str__(self):
        return self.id

    def set_variables(self, variable_value_map: dict):
        for variable, value in variable_value_map.items():
            VariableValues.objects.create(
                run=self,
                variable=variable,
                value=value,
            )


class RunVariableValues(models.Model):
    class Meta:
        verbose_name_plural = "Run Variable Values"
        constraints = [
            models.UniqueConstraint(
                fields=["run", "variable"],
                name="unique_variable_and_value",
            )
        ]

    run = models.ForeignKey(
        Runs,
        on_delete=models.CASCADE,
    )
    variable = models.ForeignKey(
        Variables,
        on_delete=models.CASCADE,
    )
    value = models.ForeignKey(
        VariableValues,
        on_delete=models.CASCADE,
    )

    def __str__(self):
        return f"{self.run} - {self.variable.name}: {self.value.name}"
