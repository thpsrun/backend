from django.core.exceptions import ValidationError
from django.db import models

from srl.constants import is_youtube_url
from srl.models.base import METHOD_TO_TIME_FIELD
from srl.models.categories import Categories
from srl.models.games import Games
from srl.models.levels import Levels
from srl.models.platforms import Platforms
from srl.models.players import Players
from srl.models.variable_values import VariableValues
from srl.models.variables import Variables
from srl.timing import ResolvedTiming, resolve_timing


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
            models.Index(
                fields=["game", "category", "level", "obsolete"],
                name="idx_runs_game_cat_level_obs",
            ),
            models.Index(
                fields=["vid_status"],
                name="idx_runs_vid_status",
            ),
            models.Index(
                fields=["obsolete"],
                name="idx_runs_obsolete",
            ),
            models.Index(
                fields=["date"],
                name="idx_runs_date",
            ),
            models.Index(
                fields=["vid_status", "obsolete", "place"],
                name="idx_runs_vstatus_obs_place",
            ),
        ]

    class VidStatus(models.TextChoices):
        VERIFIED = "verified", "Verified"
        NEW = "new", "Unverified"
        REJECTED = "rejected", "Rejected"
        REVIEW = "review", "Under Review"

    class RunType(models.TextChoices):
        MAIN = "main", "Full Game"
        IL = "il", "Individual Level"

    id = models.CharField(
        max_length=10,
        primary_key=True,
        verbose_name="Run ID",
    )
    runtype = models.CharField(
        max_length=5,
        choices=RunType.choices,
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
        on_delete=models.PROTECT,
    )
    level = models.ForeignKey(
        Levels,
        verbose_name="Level",
        blank=True,
        null=True,
        on_delete=models.PROTECT,
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
        on_delete=models.PROTECT,
    )
    emulated = models.BooleanField(
        verbose_name="Emulated?",
        default=False,
    )
    vid_status = models.CharField(
        verbose_name="SRC Status",
        choices=VidStatus.choices,
        default=VidStatus.VERIFIED,
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
        on_delete=models.PROTECT,
        related_name="approved_runs",
    )
    obsolete = models.BooleanField(
        verbose_name="Obsolete?",
        default=False,
        help_text=(
            "When True, the run will be considered obsolete. Points will not "
            "count towards the player's total."
        ),
    )
    obsoleted_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text=("Should only be occupied if `obsolte` is true."),
    )
    review_notes = models.TextField(
        blank=True,
        default="",
        verbose_name="Moderator Review Notes",
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
        db_index=True,
    )
    updated_at = models.DateTimeField(
        auto_now=True,
    )
    import_issues = models.JSONField(
        default=list,
        blank=True,
        verbose_name="Import Issues",
    )
    has_import_issues = models.BooleanField(
        default=False,
        db_index=True,
        verbose_name="Has Import Issues",
    )

    _TIMING_FIELD_MAP: dict[str, tuple[str, str]] = {
        method: (secs_field.removesuffix("_secs"), secs_field)
        for method, secs_field in METHOD_TO_TIME_FIELD.items()
    }

    def _resolved_timing(
        self,
    ) -> ResolvedTiming:
        rvvs = sorted(
            self.runvariablevalues_set.all(),  # type: ignore
            key=lambda r: r.variable_id,
        )
        values: list[VariableValues] = []
        for rvv in rvvs:
            rvv.value.var = rvv.variable
            values.append(rvv.value)
        return resolve_timing(
            game=self.game,
            category=self.category,
            is_il=(self.runtype == "il"),
            variable_values=values,
        )

    def _primary_timing_method(
        self,
    ) -> str:
        return self._resolved_timing().primary_method

    def _resolved_required_methods(
        self,
    ) -> list[str]:
        return self._resolved_timing().required_methods

    def validate_allowed_method_data(
        self,
    ) -> None:
        """Enforce that the run has data for every resolved "allowed" timing method.

        Resolves the `Game` -> `Category` -> `Variable` -> `VariableValue` chain to resolve if
        the run has the `required_methods`. Missing or zero values on any resolved method
        will raise a ValidationError.
        """
        allowed = self._resolved_required_methods()
        missing: list[str] = []
        for method in allowed:
            _, secs_field = self._TIMING_FIELD_MAP[method]
            value = getattr(self, secs_field)
            if not value or value <= 0:
                missing.append(method)
        if missing:
            raise ValidationError(
                f"Run requires the following timing methods: {allowed}. "
                f"Missing or zero: {missing}",
            )

    def collect_import_issues(
        self,
    ) -> list[dict]:
        """Return import-time validation issues for this run without raising."""
        issues: list[dict] = []
        missing: list[str] = []
        for method in self._resolved_required_methods():
            _, secs_field = self._TIMING_FIELD_MAP[method]
            value = getattr(self, secs_field)
            if not value or value <= 0:
                missing.append(method)
        if missing:
            issues.append(
                {
                    "type": "missing_timing_methods",
                    "methods": missing,
                },
            )
        if self.video and not is_youtube_url(self.video):
            issues.append(
                {
                    "type": "invalid_video_host",
                    "url": self.video,
                },
            )
        return issues

    def refresh_import_issues(
        self,
    ) -> None:
        """Recompute and persist `import_issues` / `has_import_issues` for this run."""
        issues = self.collect_import_issues()
        self.import_issues = issues
        self.has_import_issues = bool(issues)
        self.save(
            update_fields=[
                "import_issues",
                "has_import_issues",
            ],
        )

    @property
    def p_time(
        self,
    ) -> str | None:
        method = self._primary_timing_method()
        field, secs_field = self._TIMING_FIELD_MAP[method]
        secs_value = getattr(self, secs_field)
        if secs_value and secs_value > 0:
            return getattr(self, field)
        for candidate in self._resolved_required_methods():
            cand_field, cand_secs = self._TIMING_FIELD_MAP[candidate]
            cand_value = getattr(self, cand_secs)
            if cand_value and cand_value > 0:
                return getattr(self, cand_field)
        return None

    @property
    def p_time_secs(
        self,
    ) -> float | None:
        method = self._primary_timing_method()
        _, secs_field = self._TIMING_FIELD_MAP[method]
        value = getattr(self, secs_field)
        if value and value > 0:
            return value
        for candidate in self._resolved_required_methods():
            _, cand_secs = self._TIMING_FIELD_MAP[candidate]
            cand_value = getattr(self, cand_secs)
            if cand_value and cand_value > 0:
                return cand_value
        return None

    def __str__(self):
        return self.id


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
