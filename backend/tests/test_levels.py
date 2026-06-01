from api.v1.routers.resources.levels import router as levels_router
from django.test import TestCase
from ninja.testing import TestClient
from srl.models import Games, Levels, Platforms

from tests.test_auth import AuthTestBase


class LevelsReadTest(TestCase):

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

        cls.level = Levels.objects.create(
            id="level1",
            game=cls.game,
            name="Warehouse",
            slug="warehouse",
            url="https://speedrun.com/test-game/Warehouse",
        )

    def setUp(
        self,
    ) -> None:
        self.client = TestClient(levels_router)  # type: ignore

    def test_list_levels(
        self,
    ) -> None:
        response = self.client.get("/all")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIsInstance(data, list)
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]["id"], "level1")
        self.assertEqual(data[0]["name"], "Warehouse")

    def test_get_level(
        self,
    ) -> None:
        response = self.client.get("/level1")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["id"], "level1")
        self.assertEqual(data["name"], "Warehouse")

    def test_level_404(
        self,
    ) -> None:
        response = self.client.get("/nonexistent")
        self.assertEqual(response.status_code, 404)
        data = response.json()
        self.assertEqual(data["error"], "Level ID does not exist")


class LevelsWriteTest(AuthTestBase):

    def setUp(
        self,
    ) -> None:
        super().setUp()
        self.client = TestClient(levels_router)  # type: ignore

    def test_create_level(
        self,
    ) -> None:
        response = self.client.post(
            "/",
            json={
                "game_id": "game1",
                "name": "School",
                "slug": "school",
                "url": "https://speedrun.com/test-game/School",
            },  # type: ignore
            headers={"X-API-Key": self.api_key},
        )
        self.assertEqual(response.status_code, 201)
        data = response.json()
        self.assertEqual(data["name"], "School")
        self.assertIsNotNone(data.get("id"))
        self.assertEqual(len(data["id"]), 8)

    def test_create_level_custom_id(
        self,
    ) -> None:
        response = self.client.post(
            "/",
            json={
                "id": "lvl001",
                "game_id": "game1",
                "name": "Warehouse",
                "slug": "warehouse",
                "url": "https://speedrun.com/test-game/Warehouse",
            },  # type: ignore
            headers={"X-API-Key": self.api_key},
        )
        self.assertEqual(response.status_code, 201)
        data = response.json()
        self.assertEqual(data["id"], "lvl001")

    def test_create_level_bad_game(
        self,
    ) -> None:
        response = self.client.post(
            "/",
            json={
                "game_id": "nonexistent",
                "name": "Level",
                "slug": "level",
                "url": "https://speedrun.com/test/Level",
            },  # type: ignore
            headers={"X-API-Key": self.api_key},
        )
        self.assertEqual(response.status_code, 404)

    def test_update_level(
        self,
    ) -> None:
        Levels.objects.create(
            id="toupdate",
            game=self.game,
            name="ToUpdate",
            slug="to-update",
            url="https://speedrun.com/test/ToUpdate",
        )

        response = self.client.put(
            "/toupdate",
            json={"name": "Updated Level"},  # type: ignore
            headers={"X-API-Key": self.api_key},
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["id"], "toupdate")
        self.assertEqual(data["name"], "Updated Level")

    def test_delete_level(
        self,
    ) -> None:
        Levels.objects.create(
            id="todelete",
            game=self.game,
            name="ToDelete",
            slug="to-delete",
            url="https://speedrun.com/test/ToDelete",
        )

        response = self.client.delete(
            "/todelete",
            headers={"X-API-Key": self.api_key},
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("deleted successfully", data["message"])
        self.assertFalse(Levels.objects.filter(id="todelete").exists())
