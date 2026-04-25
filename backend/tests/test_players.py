from api.v1.routers.resources.players import router as players_router
from django.test import TestCase
from ninja.testing import TestClient
from srl.models import CountryCodes, Players

from tests.test_auth import AuthTestBase


class PlayersReadTest(TestCase):

    @classmethod
    def setUpTestData(
        cls,
    ) -> None:
        from django.contrib.auth import get_user_model

        User = get_user_model()
        cls.user = User.objects.create_user(
            username="testplayer_owner",
            email="owner@example.com",
            password="supersecret123",
        )
        cls.user.gradient_1 = "#ff0044"
        cls.user.gradient_2 = "#ffaa00"
        cls.user.save()

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
            user=cls.user,
            claim_status=Players.ClaimStatus.CLAIMED,
        )
        cls.unclaimed = Players.objects.create(
            id="unclaim1",
            name="Unclaimed",
            url="https://speedrun.com/user/Unclaimed",
        )

    def setUp(
        self,
    ) -> None:
        self.client = TestClient(players_router)  # type: ignore

    def test_get_player(
        self,
    ) -> None:
        response = self.client.get("/player1")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["id"], "player1")
        self.assertEqual(data["player"]["name"], "TestPlayer")
        self.assertEqual(data["player"]["nickname"], "Tester")

    def test_get_player_name(
        self,
    ) -> None:
        response = self.client.get("/TestPlayer")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["id"], "player1")

    def test_get_player_nickname(
        self,
    ) -> None:
        response = self.client.get("/Tester")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["id"], "player1")

    def test_player_404(
        self,
    ) -> None:
        response = self.client.get("/nonexistent")
        self.assertEqual(response.status_code, 404)
        data = response.json()
        self.assertEqual(data["error"], "Player ID does not exist")

    def test_get_player_exposes_gradients(
        self,
    ) -> None:
        response = self.client.get("/player1")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["customizations"]["gradient_1"], "#ff0044")
        self.assertEqual(data["customizations"]["gradient_2"], "#ffaa00")
        self.assertIsNone(data["customizations"]["gradient_3"])

    def test_get_player_gradients_null_when_unclaimed(
        self,
    ) -> None:
        response = self.client.get("/unclaim1")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIsNone(data["customizations"]["gradient_1"])
        self.assertIsNone(data["customizations"]["gradient_2"])
        self.assertIsNone(data["customizations"]["gradient_3"])

    def test_search_player_exposes_gradients(
        self,
    ) -> None:
        response = self.client.get("/search?q=TestPlayer")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(len(data), 1)
        self.assertEqual(
            data[0]["gradients"],
            {
                "gradient_1": "#ff0044",
                "gradient_2": "#ffaa00",
                "gradient_3": None,
            },
        )

    def test_search_player_gradients_null_when_unclaimed(
        self,
    ) -> None:
        response = self.client.get("/search?q=Unclaimed")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(len(data), 1)
        self.assertIsNone(data[0]["gradients"])


class PlayersWriteTest(AuthTestBase):

    def setUp(
        self,
    ) -> None:
        super().setUp()
        self.client = TestClient(players_router)  # type: ignore

    def test_create_player(
        self,
    ) -> None:
        response = self.client.post(
            "/",
            json={
                "url": "https://speedrun.com/user/NewPlayer",
                "player": {"name": "NewPlayer"},
            },  # type: ignore
            headers={"X-API-Key": self.api_key},
        )
        self.assertEqual(response.status_code, 201)
        data = response.json()
        self.assertEqual(data["player"]["name"], "NewPlayer")
        self.assertIsNotNone(data.get("id"))
        self.assertEqual(len(data["id"]), 8)

    def test_create_player_custom_id(
        self,
    ) -> None:
        response = self.client.post(
            "/",
            json={
                "id": "custom01",
                "url": "https://speedrun.com/user/CustomPlayer",
                "player": {"name": "CustomPlayer"},
            },  # type: ignore
            headers={"X-API-Key": self.api_key},
        )
        self.assertEqual(response.status_code, 201)
        data = response.json()
        self.assertEqual(data["id"], "custom01")

    def test_create_player_country(
        self,
    ) -> None:
        response = self.client.post(
            "/",
            json={
                "url": "https://speedrun.com/user/PlayerWithCountry",
                "player": {
                    "name": "PlayerWithCountry",
                    "country_id": "usa",
                },
            },  # type: ignore
            headers={"X-API-Key": self.api_key},
        )
        self.assertEqual(response.status_code, 201)
        data = response.json()
        self.assertEqual(data["player"]["name"], "PlayerWithCountry")
        player = Players.objects.get(name="PlayerWithCountry")
        self.assertEqual(player.countrycode.id, "usa")  # type: ignore

    def test_create_player_duplicate(
        self,
    ) -> None:
        Players.objects.create(
            id="existing",
            name="Existing",
            url="https://speedrun.com/user/Existing",
        )

        response = self.client.post(
            "/",
            json={
                "id": "existing",
                "url": "https://speedrun.com/user/Another",
                "player": {"name": "Another"},
            },  # type: ignore
            headers={"X-API-Key": self.api_key},
        )
        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertEqual(data["error"], "ID Already Exists")

    def test_update_player(
        self,
    ) -> None:
        Players.objects.create(
            id="toupdate",
            name="ToUpdate",
            url="https://speedrun.com/user/ToUpdate",
        )

        response = self.client.put(
            "/toupdate",
            json={
                "player": {
                    "nickname": "UpdatedNick",
                    "pronouns": "They/Them",
                },
            },  # type: ignore
            headers={"X-API-Key": self.api_key},
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["id"], "toupdate")
        self.assertEqual(data["player"]["nickname"], "UpdatedNick")
        self.assertEqual(data["player"]["pronouns"], "They/Them")

    def test_delete_player(
        self,
    ) -> None:
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


class GradientsEmbedTest(TestCase):

    def test_gradients_embed_accepts_three_hex_strings(
        self,
    ) -> None:
        from api.v1.schemas.players import GradientsEmbed

        embed = GradientsEmbed(
            gradient_1="#ff0044",
            gradient_2="#ffaa00",
            gradient_3="#00aaff",
        )
        self.assertEqual(embed.gradient_1, "#ff0044")
        self.assertEqual(embed.gradient_2, "#ffaa00")
        self.assertEqual(embed.gradient_3, "#00aaff")

    def test_gradients_embed_allows_partial_nulls(
        self,
    ) -> None:
        from api.v1.schemas.players import GradientsEmbed

        embed = GradientsEmbed(gradient_1="#ff0044")
        self.assertEqual(embed.gradient_1, "#ff0044")
        self.assertIsNone(embed.gradient_2)
        self.assertIsNone(embed.gradient_3)


class ExtractPlayerGradientsTest(TestCase):

    @classmethod
    def setUpTestData(
        cls,
    ) -> None:
        from django.contrib.auth import get_user_model

        User = get_user_model()
        cls.user_with_colors = User.objects.create_user(
            username="grad_user",
            email="grad@example.com",
            password="supersecret123",
        )
        cls.user_with_colors.gradient_1 = "#ff0044"
        cls.user_with_colors.gradient_2 = "#ffaa00"
        cls.user_with_colors.save()

        cls.user_no_colors = User.objects.create_user(
            username="plain_user",
            email="plain@example.com",
            password="supersecret123",
        )

        cls.claimed_player = Players.objects.create(
            id="claimed01",
            name="ClaimedPlayer",
            url="https://speedrun.com/user/claimed",
            user=cls.user_with_colors,
            claim_status=Players.ClaimStatus.CLAIMED,
        )
        cls.claimed_plain = Players.objects.create(
            id="plain01",
            name="PlainPlayer",
            url="https://speedrun.com/user/plain",
            user=cls.user_no_colors,
            claim_status=Players.ClaimStatus.CLAIMED,
        )
        cls.unclaimed_player = Players.objects.create(
            id="unclaim01",
            name="UnclaimedPlayer",
            url="https://speedrun.com/user/unclaimed",
        )

    def test_returns_dict_when_user_has_any_color(
        self,
    ) -> None:
        from api.v1.schemas.players import extract_gradients

        result = extract_gradients(self.claimed_player)
        self.assertEqual(
            result,
            {
                "gradient_1": "#ff0044",
                "gradient_2": "#ffaa00",
                "gradient_3": None,
            },
        )

    def test_returns_none_when_user_has_no_colors(
        self,
    ) -> None:
        from api.v1.schemas.players import extract_gradients

        result = extract_gradients(self.claimed_plain)
        self.assertIsNone(result)

    def test_returns_none_when_player_has_no_linked_user(
        self,
    ) -> None:
        from api.v1.schemas.players import extract_gradients

        result = extract_gradients(self.unclaimed_player)
        self.assertIsNone(result)
