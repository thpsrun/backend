import datetime
from io import StringIO

from api.v1.routers.resources.runs import router as runs_router
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone
from ninja.testing import TestClient
from srl.models import (
    Categories,
    CountryCodes,
    Games,
    Levels,
    Platforms,
    Players,
    RunPlayers,
    Runs,
)
from srl.models.base import LeaderboardChoices

from tests.test_auth import AuthTestBase


class RunsReadTest(TestCase):

    @classmethod
    def setUpTestData(
        cls,
    ) -> None:
        cls.platform = Platforms.objects.create(
            id="pc",
            name="PC",
            slug="pc",
        )
        cls.game = Games.objects.create(
            id="game1",
            name="Test Game",
            slug="test-game",
            twitch="Test Game",
            release="2000-01-01",
            boxart="https://speedrun.com/game1/cover",
            defaulttime="rta",
            idefaulttime="rta",
            pointsmax=1000,
            ipointsmax=100,
        )
        cls.game.platforms.add("pc")

        cls.category = Categories.objects.create(
            id="cat1",
            game=cls.game,
            name="Any%",
            slug="any",
            type="per-game",
            url="https://speedrun.com/test-game#any",
            archive=False,
        )

        cls.country = CountryCodes.objects.create(id="usa", name="United States")
        cls.player = Players.objects.create(
            id="player1",
            name="TestPlayer",
            nickname="Tester",
            url="https://speedrun.com/user/TestPlayer",
            countrycode=cls.country,
        )

        cls.test_run = Runs.objects.create(
            id="run1",
            runtype="main",
            game=cls.game,
            category=cls.category,
            place=1,
            url="https://speedrun.com/test-game/run/run1",
            video="https://youtube.com/watch?v=abc123",
            date=timezone.make_aware(datetime.datetime(2024, 1, 1)),
            v_date=timezone.make_aware(datetime.datetime(2024, 1, 2)),
            time="5m 30s",
            time_secs=330.0,
            vid_status="verified",
        )

        RunPlayers.objects.create(
            run=cls.test_run,
            player=cls.player,
            order=1,
        )

    def setUp(
        self,
    ) -> None:
        self.client = TestClient(runs_router)  # type: ignore

    def test_list_runs(
        self,
    ) -> None:
        response = self.client.get("/all")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIsInstance(data, list)
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]["id"], "run1")

    def test_list_runs_game_filter(
        self,
    ) -> None:
        response = self.client.get("/all?game_id=game1")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIsInstance(data, list)
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]["id"], "run1")

    def test_get_run(
        self,
    ) -> None:
        response = self.client.get("/run1")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["id"], "run1")
        self.assertEqual(data["times"]["time"], "5m 30s")
        self.assertEqual(data["place"], 1)

    def test_get_run_embed_game(
        self,
    ) -> None:
        response = self.client.get("/run1?embed=game")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["id"], "run1")
        self.assertIsNotNone(data.get("game"))
        self.assertEqual(data["game"]["id"], "game1")
        self.assertEqual(data["game"]["name"], "Test Game")

    def test_get_run_players(
        self,
    ) -> None:
        response = self.client.get("/run1")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["id"], "run1")
        self.assertIsInstance(data["players"], list)
        self.assertEqual(len(data["players"]), 1)
        self.assertEqual(data["players"][0]["id"], "player1")

    def test_run_404(
        self,
    ) -> None:
        response = self.client.get("/nonexistent")
        self.assertEqual(response.status_code, 404)
        data = response.json()
        self.assertEqual(data["error"], "Run ID does not exist")

    def test_run_bad_embed(
        self,
    ) -> None:
        response = self.client.get("/run1?embed=invalid")
        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertIn("Invalid embed", data["error"])


class RunsWriteTest(AuthTestBase):

    @classmethod
    def setUpTestData(
        cls,
    ) -> None:
        super().setUpTestData()
        cls.game.required_methods_fg = [LeaderboardChoices.REALTIME]
        cls.game.required_methods_il = [LeaderboardChoices.REALTIME]
        cls.game.save()
        cls.category = Categories.objects.create(
            id="cat1",
            game=cls.game,
            name="Any%",
            slug="any",
            type="per-game",
            url="https://speedrun.com/test-game#any",
        )
        cls.level = Levels.objects.create(
            id="level1",
            game=cls.game,
            name="Warehouse",
            slug="warehouse",
            url="https://speedrun.com/test-game/Warehouse",
        )
        cls.il_category = Categories.objects.create(
            id="ilcat",
            game=cls.game,
            name="IL Any%",
            slug="il-any",
            type="per-level",
            url="https://speedrun.com/test-game#il-any",
        )
        cls.player = Players.objects.create(
            id="player1",
            name="TestPlayer",
            url="https://speedrun.com/user/TestPlayer",
        )

    def setUp(
        self,
    ) -> None:
        super().setUp()
        self.client = TestClient(runs_router)  # type: ignore

    def test_create_run(
        self,
    ) -> None:
        response = self.client.post(
            "/",
            json={
                "game_id": "game1",
                "category_id": "cat1",
                "runtype": "main",
                "place": 1,
                "url": "https://speedrun.com/test-game/run/new",
                "time": "5m 30s",
                "time_secs": 330.0,
                "player_ids": ["player1"],
            },  # type: ignore
            headers={"X-API-Key": self.api_key},
        )
        self.assertEqual(response.status_code, 201)
        data = response.json()
        self.assertEqual(data["times"]["time"], "5m 30s")
        self.assertEqual(data["place"], 1)
        self.assertIsNotNone(data.get("id"))
        self.assertEqual(len(data["id"]), 8)

    def test_create_run_custom_id(
        self,
    ) -> None:
        response = self.client.post(
            "/",
            json={
                "id": "run001",
                "game_id": "game1",
                "category_id": "cat1",
                "runtype": "main",
                "place": 2,
                "url": "https://speedrun.com/test-game/run/run001",
                "time": "6m 00s",
                "time_secs": 360.0,
            },  # type: ignore
            headers={"X-API-Key": self.api_key},
        )
        self.assertEqual(response.status_code, 201)
        data = response.json()
        self.assertEqual(data["id"], "run001")

    def test_create_run_bad_game(
        self,
    ) -> None:
        response = self.client.post(
            "/",
            json={
                "game_id": "nonexistent",
                "runtype": "main",
                "place": 1,
                "url": "https://speedrun.com/test/run/new",
            },  # type: ignore
            headers={"X-API-Key": self.api_key},
        )
        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertEqual(data["error"], "Game does not exist")

    def test_update_run(
        self,
    ) -> None:
        Runs.objects.create(
            id="toupdate",
            game=self.game,
            category=self.category,
            runtype="main",
            place=5,
            url="https://speedrun.com/test-game/run/toupdate",
            time="10m 00s",
            time_secs=600.0,
        )

        response = self.client.put(
            "/toupdate",
            json={
                "place": 1,
                "time": "5m 00s",
                "time_secs": 300.0,
            },  # type: ignore
            headers={"X-API-Key": self.api_key},
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["id"], "toupdate")
        # place is not a RunUpdateSchema field, so the place=1 in the payload is silently
        # dropped: placement is server-computed, not client-settable on update.
        self.assertEqual(data["place"], 5)
        self.assertEqual(data["times"]["time"], "5m 00s")

    def test_create_slower_run_is_obsoleted(
        self,
    ) -> None:
        """POST /runs marks a player's newly added slower run obsolete (keep-best)."""
        fast = Runs.objects.create(
            id="pbfast",
            game=self.game,
            category=self.category,
            runtype="main",
            place=1,
            url="https://speedrun.com/test-game/run/pbfast",
            time="5m 00s",
            time_secs=300.0,
            vid_status="verified",
            date=timezone.make_aware(datetime.datetime(2024, 1, 1)),
            v_date=timezone.make_aware(datetime.datetime(2024, 1, 2)),
        )
        RunPlayers.objects.create(run=fast, player=self.player, order=1)

        response = self.client.post(
            "/",
            json={
                "id": "pbslow",
                "game_id": "game1",
                "category_id": "cat1",
                "runtype": "main",
                "place": 2,
                "url": "https://speedrun.com/test-game/run/pbslow",
                "time": "6m 00s",
                "time_secs": 360.0,
                "player_ids": ["player1"],
            },  # type: ignore
            headers={"X-API-Key": self.api_key},
        )
        self.assertEqual(response.status_code, 201)
        self.assertTrue(response.json()["obsolete"])

        fast.refresh_from_db()
        slow = Runs.objects.get(id="pbslow")
        self.assertFalse(fast.obsolete)
        self.assertTrue(slow.obsolete)

    def test_create_faster_run_obsoletes_existing(
        self,
    ) -> None:
        """A newly created faster run obsoletes the same player's existing slower run."""
        slow = Runs.objects.create(
            id="oldslow",
            game=self.game,
            category=self.category,
            runtype="main",
            place=1,
            url="https://speedrun.com/test-game/run/oldslow",
            time="6m 00s",
            time_secs=360.0,
            vid_status="verified",
            date=timezone.make_aware(datetime.datetime(2024, 1, 1)),
            v_date=timezone.make_aware(datetime.datetime(2024, 1, 2)),
        )
        RunPlayers.objects.create(run=slow, player=self.player, order=1)

        response = self.client.post(
            "/",
            json={
                "id": "newfast",
                "game_id": "game1",
                "category_id": "cat1",
                "runtype": "main",
                "place": 1,
                "url": "https://speedrun.com/test-game/run/newfast",
                "time": "5m 00s",
                "time_secs": 300.0,
                "player_ids": ["player1"],
            },  # type: ignore
            headers={"X-API-Key": self.api_key},
        )
        self.assertEqual(response.status_code, 201)
        self.assertFalse(response.json()["obsolete"])

        slow.refresh_from_db()
        fast = Runs.objects.get(id="newfast")
        self.assertTrue(slow.obsolete)
        self.assertFalse(fast.obsolete)

    def test_create_does_not_obsolete_other_players(
        self,
    ) -> None:
        """Keep-best dedup is per player: a different player's run is untouched."""
        other = Players.objects.create(
            id="player2",
            name="OtherPlayer",
            url="https://speedrun.com/user/OtherPlayer",
        )
        other_run = Runs.objects.create(
            id="otherpb",
            game=self.game,
            category=self.category,
            runtype="main",
            place=1,
            url="https://speedrun.com/test-game/run/otherpb",
            time="4m 00s",
            time_secs=240.0,
            vid_status="verified",
            date=timezone.make_aware(datetime.datetime(2024, 1, 1)),
            v_date=timezone.make_aware(datetime.datetime(2024, 1, 2)),
        )
        RunPlayers.objects.create(run=other_run, player=other, order=1)

        response = self.client.post(
            "/",
            json={
                "id": "p1run",
                "game_id": "game1",
                "category_id": "cat1",
                "runtype": "main",
                "place": 2,
                "url": "https://speedrun.com/test-game/run/p1run",
                "time": "6m 00s",
                "time_secs": 360.0,
                "player_ids": ["player1"],
            },  # type: ignore
            headers={"X-API-Key": self.api_key},
        )
        self.assertEqual(response.status_code, 201)
        other_run.refresh_from_db()
        self.assertFalse(other_run.obsolete)

    def test_delete_run(
        self,
    ) -> None:
        Runs.objects.create(
            id="todelete",
            game=self.game,
            category=self.category,
            runtype="main",
            place=1,
            url="https://speedrun.com/test-game/run/todelete",
        )

        response = self.client.delete(
            "/todelete",
            headers={"X-API-Key": self.api_key},
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("deleted successfully", data["message"])
        self.assertFalse(Runs.objects.filter(id="todelete").exists())


class RunResolutionAndValidation(TestCase):

    @classmethod
    def setUpTestData(
        cls,
    ) -> None:
        cls.game = Games.objects.create(
            id="rungame1",
            name="Run Game",
            slug="run-game",
            twitch="Run Game",
            release="2000-01-01",
            boxart="https://example.com/boxart",
            defaulttime=LeaderboardChoices.INGAME,
            idefaulttime=LeaderboardChoices.REALTIME,
            pointsmax=1000,
            ipointsmax=250,
            required_methods_fg=[
                LeaderboardChoices.REALTIME,
                LeaderboardChoices.INGAME,
            ],
            required_methods_il=[LeaderboardChoices.REALTIME],
        )
        cls.cat = Categories.objects.create(
            id="runcat1",
            name="Any%",
            slug="any",
            type="per-game",
            url="https://example.com/any",
            game=cls.game,
        )

    def _new_run(
        self,
        **kwargs,
    ) -> Runs:
        # Re-fetch category from DB each time so in-memory mutations from other
        # tests (e.g. test_resolved_allowed_uses_category_when_set) do not bleed through.
        cat = Categories.objects.get(pk=self.cat.pk)
        defaults: dict = {
            "id": "runtest1",
            "game": self.game,
            "category": cat,
            "runtype": "main",
            "place": 1,
            "url": "https://example.com/run",
            "time": "0:01:00",
            "time_secs": 60.0,
            "timenl_secs": 0.0,
            "timeigt_secs": 55.0,
        }
        defaults.update(kwargs)
        return Runs(**defaults)

    def test_resolved_allowed_falls_back_to_game(
        self,
    ) -> None:
        run = self._new_run()
        self.assertEqual(
            sorted(run._resolved_required_methods()),
            sorted([LeaderboardChoices.REALTIME, LeaderboardChoices.INGAME]),
        )

    def test_resolved_allowed_uses_category_when_set(
        self,
    ) -> None:
        self.cat.required_methods = [LeaderboardChoices.REALTIME]
        self.cat.defaulttime = LeaderboardChoices.REALTIME
        self.cat.save()
        run = self._new_run()
        self.assertEqual(
            run._resolved_required_methods(),
            [LeaderboardChoices.REALTIME],
        )

    def test_il_runtype_uses_il_game_field(
        self,
    ) -> None:
        run = self._new_run(runtype="il", timeigt_secs=0.0)
        self.assertEqual(
            run._resolved_required_methods(),
            [LeaderboardChoices.REALTIME],
        )

    def test_validate_allowed_method_data_passes_when_all_present(
        self,
    ) -> None:
        self._new_run().validate_allowed_method_data()

    def test_validate_allowed_method_data_rejects_missing(
        self,
    ) -> None:
        run = self._new_run(timeigt_secs=0.0)
        with self.assertRaises(ValidationError) as cm:
            run.validate_allowed_method_data()
        self.assertIn("missing", str(cm.exception).lower())

    def test_defensive_fallback_when_primary_value_is_zero(
        self,
    ) -> None:
        run = self._new_run(timeigt_secs=0.0)
        self.assertEqual(run._primary_timing_method(), LeaderboardChoices.INGAME)
        self.assertEqual(run.p_time_secs, 60.0)


class ResolvedAllowedSQL(TestCase):

    @classmethod
    def setUpTestData(
        cls,
    ) -> None:
        cls.game = Games.objects.create(
            id="sqlgame1",
            name="SQL Game",
            slug="sql-game",
            twitch="SQL Game",
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
        cls.cat = Categories.objects.create(
            id="sqlcat1",
            name="Any%",
            slug="any",
            type="per-game",
            url="https://example.com/any",
            game=cls.game,
            required_methods=[LeaderboardChoices.REALTIME],
            defaulttime=LeaderboardChoices.REALTIME,
        )
        cls.run_obj = Runs.objects.create(
            id="sqlrun1",
            game=cls.game,
            category=cls.cat,
            runtype="main",
            place=1,
            url="https://example.com/run",
            time_secs=60.0,
            timenl_secs=0.0,
            timeigt_secs=0.0,
        )

    def test_sql_expression_uses_category_allowed(
        self,
    ) -> None:
        from api.v1.routers.utils.query_utils import annotate_resolved_allowed

        qs = annotate_resolved_allowed(Runs.objects.filter(game=self.game))
        row = qs.first()
        self.assertEqual(
            list(row.resolved_allowed),
            [LeaderboardChoices.REALTIME],
        )

    def test_sql_expression_falls_back_to_game_fg(
        self,
    ) -> None:
        from api.v1.routers.utils.query_utils import annotate_resolved_allowed

        self.cat.required_methods = None
        self.cat.save()
        qs = annotate_resolved_allowed(Runs.objects.filter(game=self.game))
        row = qs.first()
        self.assertEqual(
            sorted(row.resolved_allowed),
            sorted([LeaderboardChoices.REALTIME, LeaderboardChoices.INGAME]),
        )

    def test_sql_expression_falls_back_to_game_il(
        self,
    ) -> None:
        from api.v1.routers.utils.query_utils import annotate_resolved_allowed

        self.cat.required_methods = None
        self.cat.save()
        self.run_obj.runtype = "il"
        self.run_obj.save()
        qs = annotate_resolved_allowed(Runs.objects.filter(game=self.game))
        row = qs.first()
        self.assertEqual(
            list(row.resolved_allowed),
            [LeaderboardChoices.REALTIME],
        )


class RunsTimingSubmission(AuthTestBase):

    def setUp(
        self,
    ) -> None:
        super().setUp()
        self.platform2 = Platforms.objects.create(
            id="pc-rsub",
            name="PC RSub",
            slug="pc-rsub",
        )
        self.game2 = Games.objects.create(
            id="rsubgame1",
            name="RSub Game",
            slug="rsub-game",
            twitch="RSub Game",
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
        self.game2.platforms.add(self.platform2)
        self.cat2 = Categories.objects.create(
            id="rsubcat1",
            name="Any%",
            slug="any-rsub",
            type="per-game",
            url="https://example.com/any",
            game=self.game2,
        )
        self.client = TestClient(runs_router)  # type: ignore

    def test_post_run_missing_required_method_rejected(
        self,
    ) -> None:
        # game2 requires both REALTIME and INGAME; submit without timeigt_secs - expect 422.
        response = self.client.post(
            "/",
            json={
                "game_id": "rsubgame1",
                "category_id": "rsubcat1",
                "runtype": "main",
                "place": 1,
                "url": "https://example.com/run/missing-igt",
                "time": "1:00.000",
                "time_secs": 60.0,
            },  # type: ignore
            headers={"X-API-Key": self.api_key},
        )
        self.assertEqual(response.status_code, 422)
        data = response.json()
        self.assertEqual(data["error"], "Run timing validation failed")

    def test_post_run_with_all_required_methods_accepted(
        self,
    ) -> None:
        # game2 requires both REALTIME and INGAME; submit both > 0 - expect 201.
        response = self.client.post(
            "/",
            json={
                "game_id": "rsubgame1",
                "category_id": "rsubcat1",
                "runtype": "main",
                "place": 1,
                "url": "https://example.com/run/full-methods",
                "time": "1:00.000",
                "time_secs": 60.0,
                "timeigt": "0:58.000",
                "timeigt_secs": 58.0,
            },  # type: ignore
            headers={"X-API-Key": self.api_key},
        )
        self.assertEqual(response.status_code, 201)
        data = response.json()
        self.assertIsNotNone(data.get("id"))

    def test_put_non_timing_field_not_blocked_by_preexisting_gap(
        self,
    ) -> None:
        # A run already exists missing IGT (game2 requires both REALTIME and INGAME). An
        # archiver-style PUT that only touches a non-timing field (arch_video) must not be
        # rejected by the pre-existing timing gap it did not introduce - expect 200.
        Runs.objects.create(
            id="rsublegacy",
            game=self.game2,
            category=self.cat2,
            runtype="main",
            place=1,
            url="https://example.com/run/legacy",
            time="1:00.000",
            time_secs=60.0,
            timeigt_secs=None,
        )

        response = self.client.put(
            "/rsublegacy",
            json={
                "arch_video": "https://www.youtube.com/watch?v=archived1",
            },  # type: ignore
            headers={"X-API-Key": self.api_key},
        )
        self.assertEqual(response.status_code, 200)

        run = Runs.objects.get(id="rsublegacy")
        self.assertEqual(
            run.arch_video,
            "https://www.youtube.com/watch?v=archived1",
        )
        # The pre-existing gap is still recorded (non-blocking), not silently dropped.
        self.assertTrue(run.has_import_issues)
        self.assertTrue(
            any(
                issue["type"] == "missing_timing_methods" and "igt" in issue["methods"]
                for issue in run.import_issues
            ),
        )

    def test_put_introducing_new_gap_still_rejected(
        self,
    ) -> None:
        # A run with both required methods present; an edit that zeroes IGT introduces a new
        # gap and must still be rejected - the delta-aware check only forgives PRE-existing
        # gaps, not regressions caused by this edit. Expect 422.
        Runs.objects.create(
            id="rsubcomplete",
            game=self.game2,
            category=self.cat2,
            runtype="main",
            place=1,
            url="https://example.com/run/complete",
            time="1:00.000",
            time_secs=60.0,
            timeigt="0:58.000",
            timeigt_secs=58.0,
        )

        response = self.client.put(
            "/rsubcomplete",
            json={
                "timeigt_secs": 0.0,
            },  # type: ignore
            headers={"X-API-Key": self.api_key},
        )
        self.assertEqual(response.status_code, 422)
        data = response.json()
        self.assertEqual(data["error"], "Run timing validation failed")


class RunSchemaTimingFields(TestCase):

    def test_run_base_schema_has_resolved_fields(
        self,
    ) -> None:
        from api.v1.schemas.runs import RunBaseSchema

        fields = RunBaseSchema.model_fields
        self.assertIn("resolved_primary_method", fields)
        self.assertIn("resolved_required_methods", fields)


class BackfillRunPrimary(TestCase):

    @classmethod
    def setUpTestData(
        cls,
    ) -> None:
        cls.game = Games.objects.create(
            id="bgame1",
            name="B Game",
            slug="b-game",
            twitch="B Game",
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
        cls.cat = Categories.objects.create(
            id="bcat1",
            name="Any%",
            slug="any",
            type="per-game",
            url="https://example.com/any",
            game=cls.game,
        )

    def setUp(
        self,
    ) -> None:
        # Per-test runs since command mutates them
        self.legacy = Runs.objects.create(
            id="legacy1",
            game=self.game,
            category=self.cat,
            runtype="main",
            place=1,
            url="https://example.com/legacy",
            time_secs=60.0,
            timenl_secs=0.0,
            timeigt_secs=0.0,
        )
        self.modern = Runs.objects.create(
            id="modern1",
            game=self.game,
            category=self.cat,
            runtype="main",
            place=2,
            url="https://example.com/modern",
            time_secs=60.0,
            timenl_secs=0.0,
            timeigt_secs=55.0,
        )
        self.orphan = Runs.objects.create(
            id="orphan1",
            game=self.game,
            category=self.cat,
            runtype="main",
            place=3,
            url="https://example.com/orphan",
            time_secs=0.0,
            timenl_secs=0.0,
            timeigt_secs=0.0,
        )

    def test_backfill_copies_data_into_primary_slot(
        self,
    ) -> None:
        call_command("backfill_run_primary_data", stdout=StringIO())
        self.legacy.refresh_from_db()
        self.modern.refresh_from_db()
        self.orphan.refresh_from_db()
        # Game primary is IGT. Legacy run had RTA data, no IGT. Backfill
        # copies RTA value into the IGT slot.
        self.assertEqual(self.legacy.timeigt_secs, 60.0)
        # Modern run already had IGT data; left alone.
        self.assertEqual(self.modern.timeigt_secs, 55.0)
        # Orphan run had no data anywhere; nothing to copy from.
        self.assertEqual(self.orphan.timeigt_secs, 0.0)

    def test_backfill_is_idempotent(
        self,
    ) -> None:
        call_command("backfill_run_primary_data", stdout=StringIO())
        call_command("backfill_run_primary_data", stdout=StringIO())
        self.legacy.refresh_from_db()
        self.assertEqual(self.legacy.timeigt_secs, 60.0)

    def test_backfill_dry_run_does_not_persist(
        self,
    ) -> None:
        call_command("backfill_run_primary_data", "--dry-run", stdout=StringIO())
        self.legacy.refresh_from_db()
        self.assertEqual(self.legacy.timeigt_secs, 0.0)

    def test_backfill_game_scope(
        self,
    ) -> None:
        # Create a second game with a legacy run; --game flag should not touch it.
        other_game = Games.objects.create(
            id="bgame2",
            name="Other Game",
            slug="other-game",
            twitch="Other Game",
            release="2000-01-01",
            boxart="https://example.com/boxart2",
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
        other_cat = Categories.objects.create(
            id="bcat2",
            name="Any%",
            slug="any",
            type="per-game",
            url="https://example.com/any2",
            game=other_game,
        )
        other_run = Runs.objects.create(
            id="otherleg1",
            game=other_game,
            category=other_cat,
            runtype="main",
            place=1,
            url="https://example.com/otherlegacy",
            time_secs=60.0,
            timenl_secs=0.0,
            timeigt_secs=0.0,
        )

        call_command(
            "backfill_run_primary_data",
            "--game",
            "b-game",
            stdout=StringIO(),
        )

        self.legacy.refresh_from_db()
        other_run.refresh_from_db()
        self.assertEqual(self.legacy.timeigt_secs, 60.0)
        self.assertEqual(other_run.timeigt_secs, 0.0)
