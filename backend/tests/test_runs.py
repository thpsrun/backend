import datetime

from api.v1.routers.resources.runs import router as runs_router
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

from tests.test_auth import AuthTestBase


class RunsReadTest(TestCase):

    @classmethod
    def setUpTestData(cls) -> None:
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
            defaulttime="realtime",
            idefaulttime="realtime",
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

    def setUp(self) -> None:
        self.client = TestClient(runs_router)

    def test_list_runs(self) -> None:
        response = self.client.get("/all")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIsInstance(data, list)
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]["id"], "run1")

    def test_list_runs_game_filter(self) -> None:
        response = self.client.get("/all?game_id=game1")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIsInstance(data, list)
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]["id"], "run1")

    def test_get_run(self) -> None:
        response = self.client.get("/run1")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["id"], "run1")
        self.assertEqual(data["time"], "5m 30s")
        self.assertEqual(data["place"], 1)

    def test_get_run_embed_game(self) -> None:
        response = self.client.get("/run1?embed=game")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["id"], "run1")
        self.assertIsNotNone(data.get("game"))
        self.assertEqual(data["game"]["id"], "game1")
        self.assertEqual(data["game"]["name"], "Test Game")

    def test_get_run_players(self) -> None:
        response = self.client.get("/run1")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["id"], "run1")
        self.assertIsInstance(data["players"], list)
        self.assertEqual(len(data["players"]), 1)
        self.assertEqual(data["players"][0]["id"], "player1")

    def test_run_404(self) -> None:
        response = self.client.get("/nonexistent")
        self.assertEqual(response.status_code, 404)
        data = response.json()
        self.assertEqual(data["error"], "Run ID does not exist")

    def test_run_bad_embed(self) -> None:
        response = self.client.get("/run1?embed=invalid")
        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertIn("Invalid embed", data["error"])


class RunsWriteTest(AuthTestBase):

    @classmethod
    def setUpTestData(cls) -> None:
        super().setUpTestData()
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

    def setUp(self) -> None:
        super().setUp()
        self.client = TestClient(runs_router)

    def test_create_run(self) -> None:
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
            },
            headers={"X-API-Key": self.api_key},
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["time"], "5m 30s")
        self.assertEqual(data["place"], 1)
        self.assertIsNotNone(data.get("id"))
        self.assertEqual(len(data["id"]), 8)

    def test_create_run_custom_id(self) -> None:
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
            },
            headers={"X-API-Key": self.api_key},
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["id"], "run001")

    def test_create_run_bad_game(self) -> None:
        response = self.client.post(
            "/",
            json={
                "game_id": "nonexistent",
                "runtype": "main",
                "place": 1,
                "url": "https://speedrun.com/test/run/new",
            },
            headers={"X-API-Key": self.api_key},
        )
        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertEqual(data["error"], "Game does not exist")

    def test_update_run(self) -> None:
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
            },
            headers={"X-API-Key": self.api_key},
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["id"], "toupdate")
        self.assertEqual(data["place"], 1)
        self.assertEqual(data["time"], "5m 00s")

    def test_delete_run(self) -> None:
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
