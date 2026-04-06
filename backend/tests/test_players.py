from api.v1.routers.resources.players import router as players_router
from django.test import TestCase
from ninja.testing import TestClient
from srl.models import CountryCodes, Players

from tests.test_auth import AuthTestBase


class PlayersReadTest(TestCase):

    @classmethod
    def setUpTestData(cls) -> None:
        cls.country = CountryCodes.objects.create(id="usa", name="United States")
        cls.player = Players.objects.create(
            id="player1",
            name="TestPlayer",
            nickname="Tester",
            url="https://speedrun.com/user/TestPlayer",
            countrycode=cls.country,
            pronouns="They/Them",
            twitch="https://twitch.tv/testplayer",
            youtube="https://youtube.com/testplayer",
            twitter="https://twitter.com/testplayer",
            bluesky="https://bsky.app/testplayer",
            ex_stream=False,
        )

    def setUp(self) -> None:
        self.client = TestClient(players_router)

    def test_get_player(self) -> None:
        response = self.client.get("/player1")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["id"], "player1")
        self.assertEqual(data["name"], "TestPlayer")
        self.assertEqual(data["nickname"], "Tester")

    def test_get_player_name(self) -> None:
        response = self.client.get("/TestPlayer")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["id"], "player1")

    def test_get_player_nickname(self) -> None:
        response = self.client.get("/Tester")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["id"], "player1")

    def test_player_404(self) -> None:
        response = self.client.get("/nonexistent")
        self.assertEqual(response.status_code, 404)
        data = response.json()
        self.assertEqual(data["error"], "Player ID does not exist")


class PlayersWriteTest(AuthTestBase):

    def setUp(self) -> None:
        super().setUp()
        self.client = TestClient(players_router)

    def test_create_player(self) -> None:
        response = self.client.post(
            "/",
            json={
                "name": "NewPlayer",
                "url": "https://speedrun.com/user/NewPlayer",
            },
            headers={"X-API-Key": self.api_key},
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["name"], "NewPlayer")
        self.assertIsNotNone(data.get("id"))
        self.assertEqual(len(data["id"]), 8)

    def test_create_player_custom_id(self) -> None:
        response = self.client.post(
            "/",
            json={
                "id": "custom01",
                "name": "CustomPlayer",
                "url": "https://speedrun.com/user/CustomPlayer",
            },
            headers={"X-API-Key": self.api_key},
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["id"], "custom01")

    def test_create_player_country(self) -> None:
        response = self.client.post(
            "/",
            json={
                "name": "PlayerWithCountry",
                "url": "https://speedrun.com/user/PlayerWithCountry",
                "country_id": "usa",
            },
            headers={"X-API-Key": self.api_key},
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["name"], "PlayerWithCountry")
        player = Players.objects.get(name="PlayerWithCountry")
        self.assertEqual(player.countrycode.id, "usa")

    def test_create_player_duplicate(self) -> None:
        Players.objects.create(
            id="existing",
            name="Existing",
            url="https://speedrun.com/user/Existing",
        )

        response = self.client.post(
            "/",
            json={
                "id": "existing",
                "name": "Another",
                "url": "https://speedrun.com/user/Another",
            },
            headers={"X-API-Key": self.api_key},
        )
        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertEqual(data["error"], "ID Already Exists")

    def test_update_player(self) -> None:
        Players.objects.create(
            id="toupdate",
            name="ToUpdate",
            url="https://speedrun.com/user/ToUpdate",
        )

        response = self.client.put(
            "/toupdate",
            json={
                "nickname": "UpdatedNick",
                "pronouns": "They/Them",
            },
            headers={"X-API-Key": self.api_key},
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["id"], "toupdate")
        self.assertEqual(data["nickname"], "UpdatedNick")
        self.assertEqual(data["pronouns"], "They/Them")

    def test_delete_player(self) -> None:
        Players.objects.create(
            id="todelete",
            name="ToDelete",
            url="https://speedrun.com/user/ToDelete",
        )

        response = self.client.delete(
            "/todelete",
            headers={"X-API-Key": self.api_key},
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("deleted successfully", data["message"])
        self.assertFalse(Players.objects.filter(id="todelete").exists())
