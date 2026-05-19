from datetime import datetime, timezone
from unittest.mock import patch

from api.v1.routers.utils.cache_utils import (
    game_leaderboard_cache_key,
    lbs_runs_cache_key,
)
from api.v1.routers.utils.query_utils import _build_lbs_run_dict
from django.core.cache import caches
from django.test import TestCase
from srl.leaderboard.recalculation import process_leaderboard
from srl.models import (
    Categories,
    Games,
    Players,
    RunPlayers,
    Runs,
    Variables,
    VariableValues,
)
from srl.models.base import LeaderboardChoices


class RecalcPerRunPrimaryTest(TestCase):

    @classmethod
    def setUpTestData(
        cls,
    ) -> None:
        cls.game = Games.objects.create(
            id="recpg1",
            name="Recalc Game",
            slug="recalc-game",
            twitch="Recalc Game",
            release="2000-01-01",
            boxart="https://example.com/boxart",
            defaulttime=LeaderboardChoices.INGAME,
            idefaulttime=LeaderboardChoices.INGAME,
            pointsmax=1000,
            ipointsmax=250,
            required_methods_fg=[
                LeaderboardChoices.REALTIME,
                LeaderboardChoices.INGAME,
            ],
            required_methods_il=[LeaderboardChoices.INGAME],
        )
        cls.category = Categories.objects.create(
            id="reccat1",
            name="Any%",
            slug="any",
            type="per-game",
            url="https://example.com/any",
            game=cls.game,
        )
        cls.player_a = Players.objects.create(
            id="recpla",
            name="PlayerA",
            url="https://speedrun.com/user/PlayerA",
        )
        cls.player_b = Players.objects.create(
            id="recplb",
            name="PlayerB",
            url="https://speedrun.com/user/PlayerB",
        )

    def _make_run(
        self,
        run_id: str,
        player: Players,
        time_secs: float,
        timeigt_secs: float,
        v_date: datetime | None = None,
    ) -> Runs:
        run = Runs.objects.create(
            id=run_id,
            game=self.game,
            category=self.category,
            runtype="main",
            vid_status="verified",
            place=0,
            time_secs=time_secs,
            timenl_secs=0.0,
            timeigt_secs=timeigt_secs,
            date=v_date or datetime(2020, 1, 1, tzinfo=timezone.utc),
            v_date=v_date or datetime(2020, 1, 1, tzinfo=timezone.utc),
        )
        RunPlayers.objects.create(run=run, player=player)
        return run

    def test_no_override_chain_resolution_unchanged(
        self,
    ) -> None:
        # Both runs have full IGT data. Game primary = INGAME. Result should
        # be unchanged from pre-spec behavior.
        self._make_run("recrc", self.player_a, time_secs=200.0, timeigt_secs=120.0)
        self._make_run("recrd", self.player_b, time_secs=95.0, timeigt_secs=80.0)

        leaderboard = {
            "game_id": self.game.id,
            "category_id": self.category.id,
            "level_id": None,
            "runtype": "main",
            "variable_value_map": {},
        }
        process_leaderboard(
            leaderboard,
            dry_run=False,
            game_is_ce={self.game.id: False},
            game_time_columns={
                self.game.id: {"main": "timeigt_secs", "il": "timeigt_secs"}
            },
        )
        run_c = Runs.objects.get(id="recrc")
        run_d = Runs.objects.get(id="recrd")
        # RunD has IGT=80 < RunC IGT=120, so RunD is the WR.
        self.assertGreater(run_d.points, run_c.points)


class LbsRunDictMethodsTest(TestCase):

    @classmethod
    def setUpTestData(
        cls,
    ) -> None:
        cls.game = Games.objects.create(
            id="lbsg1",
            name="Lbs Game",
            slug="lbs-game",
            twitch="Lbs Game",
            release="2000-01-01",
            boxart="https://example.com/boxart",
            defaulttime=LeaderboardChoices.INGAME,
            idefaulttime=LeaderboardChoices.INGAME,
            pointsmax=1000,
            ipointsmax=250,
            required_methods_fg=[
                LeaderboardChoices.REALTIME,
                LeaderboardChoices.INGAME,
            ],
            required_methods_il=[
                LeaderboardChoices.REALTIME,
                LeaderboardChoices.INGAME,
            ],
        )
        cls.category_full = Categories.objects.create(
            id="lbscat1",
            name="Any%",
            slug="any",
            type="per-game",
            url="https://example.com/any",
            game=cls.game,
        )
        cls.category_narrow = Categories.objects.create(
            id="lbscat2",
            name="100%",
            slug="100",
            type="per-game",
            url="https://example.com/100",
            game=cls.game,
            required_methods=[LeaderboardChoices.INGAME],
        )
        cls.player = Players.objects.create(
            id="lbspl1",
            name="LbsPlayer",
            url="https://speedrun.com/user/LbsPlayer",
        )

    def _make_run(
        self,
        run_id: str,
        category: Categories,
        time_secs: float,
        timeigt_secs: float,
    ) -> Runs:
        run = Runs.objects.create(
            id=run_id,
            game=self.game,
            category=category,
            runtype="main",
            vid_status="verified",
            place=0,
            time_secs=time_secs,
            timenl_secs=0.0,
            timeigt_secs=timeigt_secs,
            date=datetime(2020, 1, 1, tzinfo=timezone.utc),
            v_date=datetime(2020, 1, 1, tzinfo=timezone.utc),
        )
        RunPlayers.objects.create(run=run, player=self.player)
        return run

    def test_times_is_flat_eight_field_shape(
        self,
    ) -> None:
        run = self._make_run("lbsra", self.category_full, 95.0, 120.0)
        run.refresh_from_db()
        result = _build_lbs_run_dict(run)

        # Flat shape matching RunTimesSchema. No nested methods dict, no primary marker.
        self.assertEqual(
            set(result["times"].keys()),
            {
                "time",
                "time_secs",
                "timenl",
                "timenl_secs",
                "timeigt",
                "timeigt_secs",
                "p_time",
                "p_time_secs",
            },
        )
        # Each method's stored value passes through unchanged.
        self.assertEqual(result["times"]["time_secs"], 95.0)
        self.assertEqual(result["times"]["timeigt_secs"], 120.0)
        self.assertEqual(result["times"]["timenl_secs"], 0.0)
        # Primary still resolves and matches the run's p_time property.
        self.assertEqual(result["times"]["p_time"], run.p_time)
        self.assertEqual(result["times"]["p_time_secs"], run.p_time_secs)


class CacheKeyTimingConfigTest(TestCase):

    @classmethod
    def setUpTestData(
        cls,
    ) -> None:
        cls.game = Games.objects.create(
            id="ckgame1",
            name="Cache Game",
            slug="cache-game",
            twitch="Cache Game",
            release="2000-01-01",
            boxart="https://example.com/boxart",
            defaulttime=LeaderboardChoices.REALTIME,
            idefaulttime=LeaderboardChoices.REALTIME,
            pointsmax=1000,
            ipointsmax=250,
            required_methods_fg=[
                LeaderboardChoices.REALTIME,
                LeaderboardChoices.INGAME,
            ],
            required_methods_il=[LeaderboardChoices.REALTIME],
        )
        cls.category = Categories.objects.create(
            id="ckcat1",
            name="Any%",
            slug="any",
            type="per-game",
            url="https://example.com/any",
            game=cls.game,
        )

    def setUp(
        self,
    ) -> None:
        caches["default"].clear()

    def test_game_leaderboard_cache_key_changes_on_required_methods_save(
        self,
    ) -> None:
        before = game_leaderboard_cache_key(self.game.id)
        # Modify required_methods (no Run touched). Without the spec change,
        # the key is unchanged.
        self.game.required_methods_fg = [LeaderboardChoices.REALTIME]
        self.game.save()
        caches["default"].clear()  # flush per-ts cache
        after = game_leaderboard_cache_key(self.game.id)
        self.assertNotEqual(before, after)

    def test_lbs_runs_cache_key_changes_on_category_required_methods_save(
        self,
    ) -> None:
        before = lbs_runs_cache_key(self.game.id, self.category.id)
        self.category.required_methods = [LeaderboardChoices.REALTIME]
        self.category.save()
        caches["default"].clear()
        after = lbs_runs_cache_key(self.game.id, self.category.id)
        self.assertNotEqual(before, after)


class GameTimingRecalcSignalTest(TestCase):

    @classmethod
    def setUpTestData(
        cls,
    ) -> None:
        cls.game = Games.objects.create(
            id="gtrg1",
            name="GTR Game",
            slug="gtr-game",
            twitch="GTR Game",
            release="2000-01-01",
            boxart="https://example.com/boxart",
            defaulttime=LeaderboardChoices.REALTIME,
            idefaulttime=LeaderboardChoices.REALTIME,
            pointsmax=1000,
            ipointsmax=250,
            required_methods_fg=[
                LeaderboardChoices.REALTIME,
                LeaderboardChoices.INGAME,
            ],
            required_methods_il=[LeaderboardChoices.REALTIME],
        )

    @patch("api.signals.rebackfill_game_runs.delay")
    def test_defaulttime_change_fires_rebackfill(
        self,
        mock_rebackfill,
    ) -> None:
        self.game.defaulttime = LeaderboardChoices.INGAME
        self.game.save()
        mock_rebackfill.assert_called_once_with(self.game.slug)

    @patch("api.signals.rebackfill_game_runs.delay")
    def test_required_methods_change_fires_rebackfill(
        self,
        mock_rebackfill,
    ) -> None:
        # required_methods can flip which fallback timing column a run reads,
        # so it goes through the same rebackfill+recalc chain.
        self.game.required_methods_fg = [LeaderboardChoices.REALTIME]
        self.game.save()
        mock_rebackfill.assert_called_once_with(self.game.slug)

    @patch("api.signals.rebackfill_game_runs.delay")
    def test_non_timing_change_does_not_fire(
        self,
        mock_rebackfill,
    ) -> None:
        self.game.name = "Renamed"
        self.game.save()
        mock_rebackfill.assert_not_called()


class ChildTimingRecalcSignalTest(TestCase):

    @classmethod
    def setUpTestData(
        cls,
    ) -> None:
        cls.game = Games.objects.create(
            id="ctrg1",
            name="Child Recalc Game",
            slug="ctr-game",
            twitch="Child Recalc Game",
            release="2000-01-01",
            boxart="https://example.com/boxart",
            defaulttime=LeaderboardChoices.REALTIME,
            idefaulttime=LeaderboardChoices.REALTIME,
            pointsmax=1000,
            ipointsmax=250,
            required_methods_fg=[
                LeaderboardChoices.REALTIME,
                LeaderboardChoices.INGAME,
            ],
            required_methods_il=[LeaderboardChoices.REALTIME],
        )

    @patch("api.signals.rebackfill_game_runs.delay")
    def test_category_defaulttime_change_fires_rebackfill(
        self,
        mock_rebackfill,
    ) -> None:
        cat = Categories.objects.create(
            id="ctrcat1",
            name="Any%",
            slug="any",
            type="per-game",
            url="https://example.com/any",
            game=self.game,
        )
        mock_rebackfill.reset_mock()
        cat.defaulttime = LeaderboardChoices.INGAME
        cat.save()
        mock_rebackfill.assert_called_once_with(self.game.slug)

    @patch("api.signals.rebackfill_game_runs.delay")
    def test_category_required_methods_change_fires_rebackfill(
        self,
        mock_rebackfill,
    ) -> None:
        cat = Categories.objects.create(
            id="ctrcat2",
            name="100%",
            slug="100",
            type="per-game",
            url="https://example.com/100",
            game=self.game,
        )
        mock_rebackfill.reset_mock()
        cat.required_methods = [LeaderboardChoices.INGAME]
        cat.save()
        mock_rebackfill.assert_called_once_with(self.game.slug)

    @patch("api.signals.rebackfill_game_runs.delay")
    def test_variable_defaulttime_change_fires_rebackfill(
        self,
        mock_rebackfill,
    ) -> None:
        var = Variables.objects.create(
            id="ctrvar1",
            name="Difficulty",
            slug="difficulty",
            game=self.game,
            scope="full-game",
            archive=False,
        )
        mock_rebackfill.reset_mock()
        var.defaulttime = LeaderboardChoices.INGAME
        var.save()
        mock_rebackfill.assert_called_once_with(self.game.slug)

    @patch("api.signals.rebackfill_game_runs.delay")
    def test_value_defaulttime_change_fires_rebackfill(
        self,
        mock_rebackfill,
    ) -> None:
        var = Variables.objects.create(
            id="ctrvar2",
            name="Mode",
            slug="mode",
            game=self.game,
            scope="full-game",
            archive=False,
        )
        val = VariableValues.objects.create(
            var=var,
            name="Hard",
            slug="hard",
            value="ctrval1",
            archive=False,
        )
        mock_rebackfill.reset_mock()
        val.defaulttime = LeaderboardChoices.INGAME
        val.save()
        mock_rebackfill.assert_called_once_with(self.game.slug)
