from api.v1.routers.resources.games import router as games_router
from django.core.exceptions import ValidationError
from django.test import Client, TestCase
from ninja.testing import TestClient
from srl.models import Categories, Games, Platforms
from srl.models.base import LeaderboardChoices

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
            defaulttime="rta",
            idefaulttime="rta",
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
                "defaulttime": "rta",
                "idefaulttime": "rta",
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
                "defaulttime": "rta",
                "idefaulttime": "rta",
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
                "defaulttime": "rta",
                "idefaulttime": "rta",
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
                "defaulttime": "rta",
                "idefaulttime": "rta",
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
            defaulttime="rta",
            idefaulttime="rta",
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


class GameTimingClean(TestCase):

    def _make(
        self,
        **kwargs,
    ) -> Games:
        defaults: dict = {
            "id": "gtest1",
            "name": "Test Game",
            "slug": "test-game",
            "release": "2000-01-01",
            "boxart": "https://example.com/boxart",
            "defaulttime": LeaderboardChoices.REALTIME,
            "idefaulttime": LeaderboardChoices.REALTIME,
            "pointsmax": 1000,
            "ipointsmax": 250,
            "required_methods_fg": [
                LeaderboardChoices.REALTIME,
                LeaderboardChoices.INGAME,
            ],
            "required_methods_il": [
                LeaderboardChoices.REALTIME,
                LeaderboardChoices.INGAME,
            ],
        }
        defaults.update(kwargs)
        return Games(**defaults)

    def test_defaulttime_must_be_in_required_methods_fg(
        self,
    ) -> None:
        g = self._make(
            defaulttime=LeaderboardChoices.INGAME,
            required_methods_fg=[LeaderboardChoices.REALTIME],
        )
        with self.assertRaises(ValidationError) as cm:
            g.full_clean()
        self.assertIn("defaulttime", cm.exception.message_dict)

    def test_idefaulttime_must_be_in_required_methods_il(
        self,
    ) -> None:
        g = self._make(
            idefaulttime=LeaderboardChoices.INGAME,
            required_methods_il=[LeaderboardChoices.REALTIME],
        )
        with self.assertRaises(ValidationError) as cm:
            g.full_clean()
        self.assertIn("idefaulttime", cm.exception.message_dict)

    def test_empty_required_methods_fg_rejected(
        self,
    ) -> None:
        g = self._make(required_methods_fg=[])
        with self.assertRaises(ValidationError) as cm:
            g.full_clean()
        self.assertIn("required_methods_fg", cm.exception.message_dict)

    def test_empty_required_methods_il_rejected(
        self,
    ) -> None:
        g = self._make(required_methods_il=[])
        with self.assertRaises(ValidationError) as cm:
            g.full_clean()
        self.assertIn("required_methods_il", cm.exception.message_dict)

    def test_valid_game_clean(
        self,
    ) -> None:
        self._make().full_clean()  # should not raise


class GameNarrowingCascade(TestCase):

    @classmethod
    def setUpTestData(
        cls,
    ) -> None:
        cls.game = Games.objects.create(
            id="cgame1",
            name="C Game",
            slug="c-game",
            twitch="C Game",
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
            required_methods_il=[
                LeaderboardChoices.REALTIME,
                LeaderboardChoices.INGAME,
            ],
        )
        cls.cat = Categories.objects.create(
            id="ccat1",
            name="Any%",
            slug="any",
            type="per-game",
            url="https://example.com/any",
            game=cls.game,
            required_methods=[LeaderboardChoices.INGAME],
            defaulttime=LeaderboardChoices.INGAME,
        )

    def test_game_narrowing_rejected_if_category_uses_removed_method(
        self,
    ) -> None:
        self.game.required_methods_fg = [LeaderboardChoices.REALTIME]
        with self.assertRaises(ValidationError) as cm:
            self.game.full_clean()
        self.assertIn("required_methods_fg", cm.exception.message_dict)
        self.assertIn(self.cat.id, str(cm.exception))

    def test_game_widening_always_safe(
        self,
    ) -> None:
        self.game.required_methods_fg = [
            LeaderboardChoices.REALTIME,
            LeaderboardChoices.REALTIME_NOLOADS,
            LeaderboardChoices.INGAME,
        ]
        self.game.full_clean()


class GamesTimingWriteTest(AuthTestBase):

    def setUp(
        self,
    ) -> None:
        super().setUp()
        self.platform = Platforms.objects.create(
            id="pc-tw",
            name="PC TW",
            slug="pc-tw",
        )
        self.tw_game = Games.objects.create(
            id="twgame1",
            name="TW Game",
            slug="tw-game",
            twitch="TW Game",
            release="2000-01-01",
            boxart="https://example.com/boxart",
            defaulttime=LeaderboardChoices.REALTIME,
            idefaulttime=LeaderboardChoices.REALTIME,
            pointsmax=1000,
            ipointsmax=250,
        )
        self.tw_game.platforms.add(self.platform)
        self.client = TestClient(games_router)  # type: ignore

    def test_put_game_accepts_required_methods(
        self,
    ) -> None:
        response = self.client.put(
            "/twgame1",
            json={
                "defaulttime": "rta",
                "required_methods_fg": ["rta", "igt"],
            },  # type: ignore
            headers={"X-API-Key": self.api_key},
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("rta", data["required_methods_fg"])
        self.assertIn("igt", data["required_methods_fg"])

    def test_put_game_rejects_invalid_primary(
        self,
    ) -> None:
        # defaulttime not in required_methods_fg -> model validation should reject
        response = self.client.put(
            "/twgame1",
            json={
                "defaulttime": "igt",
                "required_methods_fg": ["rta"],
            },  # type: ignore
            headers={"X-API-Key": self.api_key},
        )
        self.assertEqual(response.status_code, 422)
        data = response.json()
        self.assertIn("errors", data["details"])

    def test_post_game_with_required_methods(
        self,
    ) -> None:
        response = self.client.post(
            "/",
            json={
                "name": "Timing Test Game",
                "slug": "timing-test-game",
                "release": "2010-01-01",
                "boxart": "https://example.com/boxart.png",
                "defaulttime": "rta",
                "idefaulttime": "rta",
                "required_methods_fg": ["rta", "igt"],
                "required_methods_il": ["rta"],
            },  # type: ignore
            headers={"X-API-Key": self.api_key},
        )
        self.assertEqual(response.status_code, 201)
        data = response.json()
        self.assertIn("rta", data["required_methods_fg"])
        self.assertIn("igt", data["required_methods_fg"])

    def test_post_game_rejects_primary_not_in_allowed(
        self,
    ) -> None:
        response = self.client.post(
            "/",
            json={
                "name": "Bad Timing Game",
                "slug": "bad-timing-game",
                "release": "2010-01-01",
                "boxart": "https://example.com/boxart.png",
                "defaulttime": "igt",
                "idefaulttime": "rta",
                "required_methods_fg": ["rta"],
                "required_methods_il": ["rta"],
            },  # type: ignore
            headers={"X-API-Key": self.api_key},
        )
        self.assertEqual(response.status_code, 422)
        data = response.json()
        self.assertIn("errors", data["details"])


class GameSchemaTimingFields(TestCase):

    def test_game_base_schema_has_required_methods(
        self,
    ) -> None:
        from api.v1.schemas.games import GameBaseSchema

        fields = GameBaseSchema.model_fields
        self.assertIn("required_methods_fg", fields)
        self.assertIn("required_methods_il", fields)
