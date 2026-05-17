from api.v1.routers.resources.categories import router as categories_router
from django.core.exceptions import ValidationError
from django.test import TestCase
from ninja.testing import TestClient
from srl.models import Categories, Games, LeaderboardChoices, Platforms, Variables

from tests.test_auth import AuthTestBase


class CategoriesReadTest(TestCase):

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

    def setUp(
        self,
    ) -> None:
        self.client = TestClient(categories_router)  # type: ignore

    def test_list_categories_requires_game(
        self,
    ) -> None:
        response = self.client.get("/all")
        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertEqual(data["error"], "Please provide the game's unique ID or slug.")

    def test_list_categories(
        self,
    ) -> None:
        response = self.client.get("/all?game=game1")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIsInstance(data, list)
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]["id"], "cat1")
        self.assertEqual(data[0]["name"], "Any%")

    def test_get_category(
        self,
    ) -> None:
        response = self.client.get("/cat1")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["id"], "cat1")
        self.assertEqual(data["name"], "Any%")

    def test_category_404(
        self,
    ) -> None:
        response = self.client.get("/nonexistent")
        self.assertEqual(response.status_code, 404)
        data = response.json()
        self.assertEqual(data["error"], "Category ID Doesn't Exist")


class CategoriesWriteTest(AuthTestBase):

    def setUp(
        self,
    ) -> None:
        super().setUp()
        self.client = TestClient(categories_router)  # type: ignore

    def test_create_category(
        self,
    ) -> None:
        response = self.client.post(
            "/",
            json={
                "game_id": "game1",
                "name": "100%",
                "slug": "100-percent",
                "type": "per-game",
                "url": "https://speedrun.com/test-game#100",
            },  # type: ignore
            headers={"X-API-Key": self.api_key},
        )
        self.assertEqual(response.status_code, 201)
        data = response.json()
        self.assertEqual(data["name"], "100%")
        self.assertEqual(data["slug"], "100-percent")
        self.assertIsNotNone(data.get("id"))
        self.assertEqual(len(data["id"]), 8)

    def test_create_category_custom_id(
        self,
    ) -> None:
        response = self.client.post(
            "/",
            json={
                "id": "anyper",
                "game_id": "game1",
                "name": "Any%",
                "slug": "any-percent",
                "type": "per-game",
                "url": "https://speedrun.com/test-game#any",
            },  # type: ignore
            headers={"X-API-Key": self.api_key},
        )
        self.assertEqual(response.status_code, 201)
        data = response.json()
        self.assertEqual(data["id"], "anyper")

    def test_create_category_bad_game(
        self,
    ) -> None:
        response = self.client.post(
            "/",
            json={
                "game_id": "nonexistent",
                "name": "Any%",
                "slug": "any",
                "type": "per-game",
                "url": "https://speedrun.com/test#any",
            },  # type: ignore
            headers={"X-API-Key": self.api_key},
        )
        self.assertEqual(response.status_code, 404)

    def test_update_category(
        self,
    ) -> None:
        Categories.objects.create(
            id="toupdate",
            game=self.game,
            name="ToUpdate",
            slug="to-update",
            type="per-game",
            url="https://speedrun.com/test#toupdate",
        )

        response = self.client.put(
            "/toupdate",
            json={"name": "Updated Category"},  # type: ignore
            headers={"X-API-Key": self.api_key},
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["id"], "toupdate")
        self.assertEqual(data["name"], "Updated Category")

    def test_delete_category(
        self,
    ) -> None:
        Categories.objects.create(
            id="todelete",
            game=self.game,
            name="ToDelete",
            slug="to-delete",
            type="per-game",
            url="https://speedrun.com/test#todelete",
        )

        response = self.client.delete(
            "/todelete",
            headers={"X-API-Key": self.api_key},
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("deleted successfully", data["message"])
        self.assertFalse(Categories.objects.filter(id="todelete").exists())


class CategoryTimingClean(TestCase):

    @classmethod
    def setUpTestData(
        cls,
    ) -> None:
        cls.game = Games.objects.create(
            id="ctgame1",
            name="Cat Game",
            slug="cat-game",
            twitch="Cat Game",
            release="2000-01-01",
            boxart="https://example.com/boxart",
            defaulttime=LeaderboardChoices.INGAME,
            idefaulttime=LeaderboardChoices.REALTIME,
            pointsmax=1000,
            ipointsmax=250,
            allowed_methods_fg=[
                LeaderboardChoices.REALTIME,
                LeaderboardChoices.INGAME,
            ],
            allowed_methods_il=[
                LeaderboardChoices.REALTIME,
            ],
        )

    def _make(
        self,
        **kwargs,
    ) -> Categories:
        defaults: dict = {
            "id": "ctest1",
            "name": "Any%",
            "slug": "any",
            "type": "per-game",
            "url": "https://example.com/any",
            "game": self.game,
            "defaulttime": None,
            "allowed_methods": None,
        }
        defaults.update(kwargs)
        return Categories(**defaults)

    def test_allowed_methods_must_be_subset_of_game_fg(
        self,
    ) -> None:
        c = self._make(
            allowed_methods=[LeaderboardChoices.REALTIME_NOLOADS],
        )
        with self.assertRaises(ValidationError) as cm:
            c.full_clean()
        self.assertIn("allowed_methods", cm.exception.message_dict)

    def test_allowed_methods_must_be_subset_of_game_il_for_il_category(
        self,
    ) -> None:
        c = self._make(
            type="per-level",
            allowed_methods=[LeaderboardChoices.INGAME],
        )
        with self.assertRaises(ValidationError) as cm:
            c.full_clean()
        self.assertIn("allowed_methods", cm.exception.message_dict)

    def test_explicit_primary_required_when_narrowing_excludes_inherited(
        self,
    ) -> None:
        c = self._make(
            allowed_methods=[LeaderboardChoices.REALTIME],
            defaulttime=None,
        )
        with self.assertRaises(ValidationError) as cm:
            c.full_clean()
        self.assertIn("defaulttime", cm.exception.message_dict)

    def test_explicit_primary_satisfies_narrowing_rule(
        self,
    ) -> None:
        c = self._make(
            allowed_methods=[LeaderboardChoices.REALTIME],
            defaulttime=LeaderboardChoices.REALTIME,
        )
        c.full_clean()

    def test_explicit_defaulttime_must_be_in_allowed_methods(
        self,
    ) -> None:
        c = self._make(
            allowed_methods=[LeaderboardChoices.REALTIME],
            defaulttime=LeaderboardChoices.INGAME,
        )
        with self.assertRaises(ValidationError) as cm:
            c.full_clean()
        self.assertIn("defaulttime", cm.exception.message_dict)

    def test_empty_allowed_methods_list_rejected(
        self,
    ) -> None:
        c = self._make(allowed_methods=[])
        with self.assertRaises(ValidationError) as cm:
            c.full_clean()
        self.assertIn("allowed_methods", cm.exception.message_dict)

    def test_null_allowed_methods_inherits_silently(
        self,
    ) -> None:
        self._make(allowed_methods=None).full_clean()


class CategoryNarrowingCascade(TestCase):

    @classmethod
    def setUpTestData(
        cls,
    ) -> None:
        cls.game = Games.objects.create(
            id="ccgame1",
            name="CC Game",
            slug="cc-game",
            twitch="CC Game",
            release="2000-01-01",
            boxart="https://example.com/boxart",
            defaulttime=LeaderboardChoices.REALTIME,
            idefaulttime=LeaderboardChoices.REALTIME,
            pointsmax=1000,
            ipointsmax=250,
            allowed_methods_fg=[
                LeaderboardChoices.REALTIME,
                LeaderboardChoices.INGAME,
            ],
            allowed_methods_il=[
                LeaderboardChoices.REALTIME,
                LeaderboardChoices.INGAME,
            ],
        )
        cls.cat = Categories.objects.create(
            id="cccat1",
            name="Any%",
            slug="any",
            type="per-game",
            url="https://example.com/any",
            game=cls.game,
        )
        cls.var = Variables.objects.create(
            id="ccvar1",
            name="V",
            slug="v",
            scope="full-game",
            game=cls.game,
            cat=cls.cat,
            allowed_methods=[LeaderboardChoices.INGAME],
            defaulttime=LeaderboardChoices.INGAME,
        )

    def test_category_narrowing_rejected_if_variable_uses_removed_method(
        self,
    ) -> None:
        self.cat.allowed_methods = [LeaderboardChoices.REALTIME]
        self.cat.defaulttime = LeaderboardChoices.REALTIME
        with self.assertRaises(ValidationError) as cm:
            self.cat.full_clean()
        self.assertIn("allowed_methods", cm.exception.message_dict)


class CategorySchemaTimingFields(TestCase):

    def test_category_base_schema_has_timing_fields(
        self,
    ) -> None:
        from api.v1.schemas.categories import CategoryBaseSchema
        fields = CategoryBaseSchema.model_fields
        self.assertIn("defaulttime", fields)
        self.assertIn("allowed_methods", fields)
