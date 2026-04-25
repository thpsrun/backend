from api.v1.routers.resources.games import router as games_router
from django.test import Client, TestCase
from ninja.testing import TestClient
from srl.models import Games, Platforms

from tests.test_auth import AuthTestBase


class GamesReadTest(TestCase):

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
            defaulttime="realtime",
            idefaulttime="realtime",
            pointsmax=1000,
            ipointsmax=100,
        )
        cls.game.platforms.add("pc")

    def setUp(
        self,
    ) -> None:
        self.client = TestClient(games_router)  # type: ignore

    def test_list_games(
        self,
    ) -> None:
        response = self.client.get("/all")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIsInstance(data, list)
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]["id"], "game1")
        self.assertEqual(data[0]["name"], "Test Game")

    def test_get_game(
        self,
    ) -> None:
        response = self.client.get("/game1")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["id"], "game1")
        self.assertEqual(data["name"], "Test Game")
        self.assertEqual(data["slug"], "test-game")

    def test_get_game_slug(
        self,
    ) -> None:
        response = self.client.get("/test-game")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["id"], "game1")

    def test_game_404(
        self,
    ) -> None:
        response = self.client.get("/nonexistent")
        self.assertEqual(response.status_code, 404)
        data = response.json()
        self.assertEqual(data["error"], "Game does not exist")


class GamesWriteTest(AuthTestBase):

    def setUp(
        self,
    ) -> None:
        super().setUp()
        self.client = TestClient(games_router)  # type: ignore

    def test_create_game(
        self,
    ) -> None:
        response = self.client.post(
            "/",
            json={
                "name": "New Test Game",
                "slug": "new-test-game",
                "twitch": "New Test Game",
                "release": "2024-06-15",
                "boxart": "https://example.com/boxart.png",
                "defaulttime": "realtime",
                "idefaulttime": "realtime",
            },  # type: ignore
            headers={"X-API-Key": self.api_key},
        )
        self.assertEqual(response.status_code, 201)
        data = response.json()
        self.assertEqual(data["name"], "New Test Game")
        self.assertEqual(data["slug"], "new-test-game")
        self.assertIsNotNone(data.get("id"))
        self.assertEqual(len(data["id"]), 8)

    def test_create_game_custom_id(
        self,
    ) -> None:
        response = self.client.post(
            "/",
            json={
                "id": "customid",
                "name": "Custom ID Game",
                "slug": "custom-id-game",
                "twitch": "Custom ID Game",
                "release": "2024-06-15",
                "boxart": "https://example.com/boxart.png",
                "defaulttime": "realtime",
                "idefaulttime": "realtime",
            },  # type: ignore
            headers={"X-API-Key": self.api_key},
        )
        self.assertEqual(response.status_code, 201)
        data = response.json()
        self.assertEqual(data["id"], "customid")

    def test_game_duplicate(
        self,
    ) -> None:
        response = self.client.post(
            "/",
            json={
                "id": "game1",
                "name": "Duplicate ID Game",
                "slug": "dup-id-game",
                "twitch": "Duplicate ID Game",
                "release": "2024-06-15",
                "boxart": "https://example.com/boxart.png",
                "defaulttime": "realtime",
                "idefaulttime": "realtime",
            },  # type: ignore
            headers={"X-API-Key": self.api_key},
        )
        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertEqual(data["error"], "ID Already Exists")

    def test_create_unauthenticated(
        self,
    ) -> None:
        full_client = Client()
        response = full_client.post(
            "/api/v1/games/",
            data={
                "name": "Unauthorized Game",
                "slug": "unauth-game",
                "twitch": "Unauthorized Game",
                "release": "2024-06-15",
                "boxart": "https://example.com/boxart.png",
                "defaulttime": "realtime",
                "idefaulttime": "realtime",
            },
            content_type="application/json",
            HTTP_X_API_KEY="invalid.key.here",
        )
        self.assertEqual(response.status_code, 401)
        self.assertFalse(Games.objects.filter(name="Unauthorized Game").exists())

    def test_update_game(
        self,
    ) -> None:
        response = self.client.put(
            "/game1",
            json={
                "name": "Updated Game Name",
                "slug": "updated-game",
            },  # type: ignore
            headers={"X-API-Key": self.api_key},
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["id"], "game1")
        self.assertEqual(data["name"], "Updated Game Name")
        self.assertEqual(data["slug"], "updated-game")

    def test_update_game_404(
        self,
    ) -> None:
        response = self.client.put(
            "/nonexistent",
            json={"name": "Updated Name", "slug": "updated"},  # type: ignore
            headers={"X-API-Key": self.api_key},
        )
        self.assertEqual(response.status_code, 404)

    def test_delete_game(
        self,
    ) -> None:
        Games.objects.create(
            id="todelete",
            name="To Delete",
            slug="to-delete",
            twitch="To Delete",
            release="2024-01-01",
            boxart="https://example.com/boxart.png",
            defaulttime="realtime",
            idefaulttime="realtime",
        )

        response = self.client.delete(
            "/todelete",
            headers={"X-API-Key": self.api_key},
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("deleted successfully", data["message"])

        self.assertFalse(Games.objects.filter(id="todelete").exists())

    def test_delete_game_404(
        self,
    ) -> None:
        response = self.client.delete(
            "/nonexistent",
            headers={"X-API-Key": self.api_key},
        )
        self.assertEqual(response.status_code, 404)
