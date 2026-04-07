from api.v1.routers.resources.variables import router as variables_router
from django.test import TestCase
from ninja.testing import TestClient
from srl.models import Categories, Games, Platforms, Variables, VariableValues

from tests.test_auth import AuthTestBase


class VariablesReadTest(TestCase):

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

        cls.variable = Variables.objects.create(
            id="var1",
            name="Difficulty",
            slug="difficulty",
            game=cls.game,
            cat=cls.category,
            scope="full-game",
            archive=False,
        )

        cls.value = VariableValues.objects.create(
            var=cls.variable,
            name="Normal",
            slug="normal",
            value="val1",
            archive=False,
        )

    def setUp(self) -> None:
        self.client = TestClient(variables_router)  # type: ignore

    def test_list_variables(self) -> None:
        response = self.client.get("/all")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIsInstance(data, list)
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]["id"], "var1")
        self.assertEqual(data[0]["name"], "Difficulty")

    def test_get_variable(self) -> None:
        response = self.client.get("/var1")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["id"], "var1")
        self.assertEqual(data["name"], "Difficulty")
        self.assertIsNotNone(data.get("values"))

    def test_variable_404(self) -> None:
        response = self.client.get("/nonexistent")
        self.assertEqual(response.status_code, 404)
        data = response.json()
        self.assertEqual(data["error"], "Variable ID does not exist")


class VariablesWriteTest(AuthTestBase):

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

    def setUp(self) -> None:
        super().setUp()
        self.client = TestClient(variables_router)  # type: ignore

    def test_create_variable(self) -> None:
        response = self.client.post(
            "/",
            json={
                "game_id": "game1",
                "name": "Difficulty",
                "slug": "difficulty",
                "scope": "full-game",
            },  # type: ignore
            headers={"X-API-Key": self.api_key},
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["name"], "Difficulty")
        self.assertIsNotNone(data.get("id"))
        self.assertEqual(len(data["id"]), 8)

    def test_create_variable_custom_id(self) -> None:
        response = self.client.post(
            "/",
            json={
                "id": "var001",
                "game_id": "game1",
                "name": "Version",
                "slug": "version",
                "scope": "full-game",
            },  # type: ignore
            headers={"X-API-Key": self.api_key},
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["id"], "var001")

    def test_create_variable_category(self) -> None:
        response = self.client.post(
            "/",
            json={
                "game_id": "game1",
                "category_id": "cat1",
                "name": "Subcategory",
                "slug": "subcategory",
                "scope": "full-game",
            },  # type: ignore
            headers={"X-API-Key": self.api_key},
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["name"], "Subcategory")
        variable = Variables.objects.get(name="Subcategory")
        self.assertEqual(variable.cat.id, "cat1")  # type: ignore

    def test_update_variable(self) -> None:
        Variables.objects.create(
            id="toupdate",
            game=self.game,
            name="ToUpdate",
            slug="to-update",
            scope="full-game",
        )

        response = self.client.put(
            "/toupdate",
            json={"name": "Updated Variable"},  # type: ignore
            headers={"X-API-Key": self.api_key},
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["id"], "toupdate")
        self.assertEqual(data["name"], "Updated Variable")

    def test_delete_variable(self) -> None:
        Variables.objects.create(
            id="todelete",
            game=self.game,
            name="ToDelete",
            slug="to-delete",
            scope="full-game",
        )

        response = self.client.delete(
            "/todelete",
            headers={"X-API-Key": self.api_key},
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("deleted successfully", data["message"])
        self.assertFalse(Variables.objects.filter(id="todelete").exists())


class VarValuesReadTest(TestCase):

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

        cls.variable = Variables.objects.create(
            id="var1",
            name="Difficulty",
            slug="difficulty",
            game=cls.game,
            scope="full-game",
            archive=False,
        )

        cls.value1 = VariableValues.objects.create(
            var=cls.variable,
            name="Normal",
            slug="normal",
            value="val1",
            archive=False,
            rules="Normal difficulty rules",
        )

        cls.value2 = VariableValues.objects.create(
            var=cls.variable,
            name="Hard",
            slug="hard",
            value="val2",
            archive=False,
            rules="Hard difficulty rules",
        )

    def setUp(self) -> None:
        self.client = TestClient(variables_router)  # type: ignore

    def test_list_values_requires_var(self) -> None:
        response = self.client.get("/values/all")
        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertEqual(data["error"], "Please provide the variable's unique ID.")

    def test_list_values(self) -> None:
        response = self.client.get("/values/all?variable_id=var1")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIsInstance(data, list)
        self.assertEqual(len(data), 2)
        names = [v["name"] for v in data]
        self.assertIn("Normal", names)
        self.assertIn("Hard", names)

    def test_list_values_embed(self) -> None:
        response = self.client.get("/values/all?variable_id=var1&embed=variable")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIsInstance(data, list)
        for value in data:
            self.assertIsNotNone(value.get("variable"))
            self.assertEqual(value["variable"]["id"], "var1")
            self.assertEqual(value["variable"]["name"], "Difficulty")

    def test_list_values_bad_embed(self) -> None:
        response = self.client.get("/values/all?variable_id=var1&embed=invalid")
        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertIn("Invalid embed", data["error"])

    def test_list_values_bad_var(self) -> None:
        response = self.client.get("/values/all?variable_id=nonexistent")
        self.assertEqual(response.status_code, 404)
        data = response.json()
        self.assertEqual(data["error"], "Variable does not exist")

    def test_get_value(self) -> None:
        response = self.client.get("/values/val1")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["value"], "val1")
        self.assertEqual(data["name"], "Normal")
        self.assertEqual(data["slug"], "normal")
        self.assertEqual(data["rules"], "Normal difficulty rules")

    def test_get_value_embed(self) -> None:
        response = self.client.get("/values/val1?embed=variable")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["value"], "val1")
        self.assertIsNotNone(data.get("variable"))
        self.assertEqual(data["variable"]["id"], "var1")
        self.assertEqual(data["variable"]["name"], "Difficulty")

    def test_value_404(self) -> None:
        response = self.client.get("/values/noexist")
        self.assertEqual(response.status_code, 404)
        data = response.json()
        self.assertEqual(data["error"], "Variable value does not exist")

    def test_value_id_too_long(self) -> None:
        response = self.client.get("/values/thisiswaytoolong")
        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertEqual(data["error"], "Value ID must be 10 characters or less")


class VarValuesWriteTest(AuthTestBase):

    @classmethod
    def setUpTestData(cls) -> None:
        super().setUpTestData()
        cls.variable = Variables.objects.create(
            id="var1",
            name="Difficulty",
            slug="difficulty",
            game=cls.game,
            scope="full-game",
            archive=False,
        )

        cls.value = VariableValues.objects.create(
            var=cls.variable,
            name="Normal",
            slug="normal",
            value="val1",
            archive=False,
        )

    def setUp(self) -> None:
        super().setUp()
        self.client = TestClient(variables_router)  # type: ignore

    def test_create_value(self) -> None:
        response = self.client.post(
            "/values/",
            json={
                "variable_id": "var1",
                "name": "Easy",
                "rules": "Easy difficulty rules",
            },  # type: ignore
            headers={"X-API-Key": self.api_key},
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["name"], "Easy")
        self.assertEqual(data["slug"], "easy")
        self.assertEqual(data["rules"], "Easy difficulty rules")
        self.assertIsNotNone(data.get("value"))
        self.assertEqual(len(data["value"]), 8)

    def test_create_value_custom_id(self) -> None:
        response = self.client.post(
            "/values/",
            json={
                "value": "hardmode",
                "variable_id": "var1",
                "name": "Hard Mode",
                "slug": "hard-mode",
            },  # type: ignore
            headers={"X-API-Key": self.api_key},
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["value"], "hardmode")
        self.assertEqual(data["name"], "Hard Mode")
        self.assertEqual(data["slug"], "hard-mode")

    def test_create_value_duplicate(self) -> None:
        response = self.client.post(
            "/values/",
            json={
                "value": "val1",
                "variable_id": "var1",
                "name": "Duplicate",
            },  # type: ignore
            headers={"X-API-Key": self.api_key},
        )
        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertEqual(data["error"], "Value ID Already Exists")

    def test_create_value_bad_var(self) -> None:
        response = self.client.post(
            "/values/",
            json={
                "variable_id": "nonexistent",
                "name": "Test",
            },  # type: ignore
            headers={"X-API-Key": self.api_key},
        )
        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertEqual(data["error"], "Variable does not exist")

    def test_update_value(self) -> None:
        response = self.client.put(
            "/values/val1",
            json={
                "name": "Updated Normal",
                "rules": "Updated rules",
                "archive": True,
            },  # type: ignore
            headers={"X-API-Key": self.api_key},
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["value"], "val1")
        self.assertEqual(data["name"], "Updated Normal")
        self.assertEqual(data["rules"], "Updated rules")
        self.assertEqual(data["archive"], True)

    def test_update_value_reparent(self) -> None:
        Variables.objects.create(
            id="var2",
            name="Platform",
            slug="platform",
            game=self.game,
            scope="full-game",
        )

        response = self.client.put(
            "/values/val1",
            json={"variable_id": "var2"},  # type: ignore
            headers={"X-API-Key": self.api_key},
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["value"], "val1")

        val = VariableValues.objects.get(value="val1")
        self.assertEqual(val.var.id, "var2")  # type: ignore

    def test_update_value_404(self) -> None:
        response = self.client.put(
            "/values/nonexistent",
            json={"name": "Updated"},  # type: ignore
            headers={"X-API-Key": self.api_key},
        )
        self.assertEqual(response.status_code, 404)
        data = response.json()
        self.assertEqual(data["error"], "Variable value does not exist")

    def test_delete_value(self) -> None:
        VariableValues.objects.create(
            var=self.variable,
            name="ToDelete",
            slug="to-delete",
            value="todel",
            archive=False,
        )

        response = self.client.delete(
            "/values/todel",
            headers={"X-API-Key": self.api_key},
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("deleted successfully", data["message"])
        self.assertFalse(VariableValues.objects.filter(value="todel").exists())

    def test_delete_value_404(self) -> None:
        response = self.client.delete(
            "/values/nonexistent",
            headers={"X-API-Key": self.api_key},
        )
        self.assertEqual(response.status_code, 404)
        data = response.json()
        self.assertEqual(data["error"], "Variable value does not exist")
