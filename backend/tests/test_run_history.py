from datetime import datetime
from datetime import timezone as _tz

from django.conf import settings
from django.db import IntegrityError, transaction
from django.test import TestCase
from srl.leaderboard.recalculation import process_leaderboard
from srl.leaderboard.resolution import resolve_leaderboard
from srl.models import Categories, Games, RunHistory, RunHistoryEndReason, Runs


class RunHistoryOpenRowConstraintTests(TestCase):
    """The database must allow at most one open (end_date IS NULL) history row per run."""

    @classmethod
    def setUpTestData(
        cls,
    ) -> None:
        """Create the minimal game/category/run graph RunHistory rows hang off of."""
        cls.game = Games.objects.create(
            id="jy65g3de",
            name="THPS1",
            slug="thps1",
            twitch="THPS1",
            release="2000-01-01",
            boxart="https://x.invalid/c",
            defaulttime="rta",
            idefaulttime="rta",
            pointsmax=1000,
            ipointsmax=100,
        )
        cls.cat = Categories.objects.create(
            id="wkpjr8kr",
            game=cls.game,
            name="Any%",
            type="per-game",
            defaulttime="rta",
        )
        cls.target_run = Runs.objects.create(
            id="run1",
            game=cls.game,
            category=cls.cat,
            runtype="main",
            place=1,
            vid_status="verified",
            obsolete=False,
            points=1000,
            time_secs=300.0,
            date=datetime(2024, 1, 1, tzinfo=_tz.utc),
        )

    def test_second_open_history_row_is_rejected(
        self,
    ) -> None:
        """Two simultaneously-open points periods for one run must be impossible."""
        RunHistory.objects.create(
            run=self.target_run,
            start_date=datetime(2024, 1, 1, tzinfo=_tz.utc),
            points=1000,
        )
        with self.assertRaises(IntegrityError), transaction.atomic():
            RunHistory.objects.create(
                run=self.target_run,
                start_date=datetime(2024, 2, 1, tzinfo=_tz.utc),
                points=900,
            )

    def test_closed_rows_do_not_conflict_with_open_row(
        self,
    ) -> None:
        """Closed periods never collide with each other or with the single open period."""
        RunHistory.objects.create(
            run=self.target_run,
            start_date=datetime(2024, 1, 1, tzinfo=_tz.utc),
            end_date=datetime(2024, 2, 1, tzinfo=_tz.utc),
            end_reason=RunHistoryEndReason.LOST_WR,
            points=1000,
        )
        RunHistory.objects.create(
            run=self.target_run,
            start_date=datetime(2024, 2, 1, tzinfo=_tz.utc),
            points=900,
        )
        self.assertEqual(self.target_run.history.count(), 2)


class RecomputeStaleOpenRowTests(TestCase):
    """A leaderboard rebuild must not collide with a stale open history row."""

    @classmethod
    def setUpTestData(
        cls,
    ) -> None:
        """Create a single verified run that becomes the WR of an empty-variant board."""
        cls.game = Games.objects.create(
            id="jy65g3de",
            name="THPS1",
            slug="thps1",
            twitch="THPS1",
            release="2000-01-01",
            boxart="https://x.invalid/c",
            defaulttime="rta",
            idefaulttime="rta",
            pointsmax=1000,
            ipointsmax=100,
        )
        cls.cat = Categories.objects.create(
            id="wkpjr8kr",
            game=cls.game,
            name="Any%",
            type="per-game",
            defaulttime="rta",
        )
        cls.wr_run = Runs.objects.create(
            id="run1",
            game=cls.game,
            category=cls.cat,
            runtype="main",
            place=1,
            vid_status="verified",
            obsolete=False,
            points=1000,
            time_secs=300.0,
            date=datetime(2024, 1, 1, tzinfo=_tz.utc),
        )

    def test_rebuild_replaces_stale_open_row_without_conflict(
        self,
    ) -> None:
        """A stale open row left behind by a divergent clear is replaced, not collided with."""
        # Simulate the open row that escaped the variant-scoped clear: an older,
        # still-open period from a previous recompute.
        RunHistory.objects.create(
            run=self.wr_run,
            start_date=datetime(2020, 1, 1, tzinfo=_tz.utc),
            points=500,
        )

        leaderboard = resolve_leaderboard(self.wr_run)
        # Must not raise IntegrityError on `unique_open_runhistory_per_run`.
        process_leaderboard(
            leaderboard,
            dry_run=False,
            game_is_ce={self.game.id: False},
        )

        open_rows = self.wr_run.history.filter(end_date__isnull=True)
        self.assertEqual(open_rows.count(), 1)
        # The surviving open row is the freshly rebuilt WR period, not the stale one.
        surviving = open_rows.first()
        self.assertEqual(surviving.points, settings.POINTS_MAX_FG)
        self.assertEqual(
            surviving.start_date,
            datetime(2024, 1, 1, tzinfo=_tz.utc),
        )
