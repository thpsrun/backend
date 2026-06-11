from datetime import datetime
from datetime import timezone as _tz

from django.db import IntegrityError, transaction
from django.test import TestCase
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
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
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
