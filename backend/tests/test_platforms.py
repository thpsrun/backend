from api.v1.routers.resources.platforms import router as platforms_router
from django.test import TestCase
from ninja.testing import TestClient
from srl.models import Platforms

from tests.test_auth import AuthTestBase


class PlatformsReadTest(TestCase):

    @classmethod
    def setUpTestData(
        cls,
    ) -> None:
        cls.platform = Platforms.objects.create(
            id="pc",
            name="PC",
            slug="pc",
        )

    def setUp(
        self,
    ) -> None:
        self.client = TestClient(platforms_router)  # type: ignore

    def test_list_platforms(
        self,
    ) -> None:
        response = self.client.get("/all")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIsInstance(data, list)
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]["id"], "pc")
        self.assertEqual(data[0]["name"], "PC")

    def test_get_platform(
        self,
    ) -> None:
        response = self.client.get("/pc")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["id"], "pc")
        self.assertEqual(data["name"], "PC")

    def test_platform_404(
        self,
    ) -> None:
        response = self.client.get("/nonexistent")
        self.assertEqual(response.status_code, 404)
        data = response.json()
        self.assertEqual(data["error"], "Platform ID does not exist")


class PlatformsWriteTest(AuthTestBase):

    def setUp(
        self,
    ) -> None:
        super().setUp()
        self.client = TestClient(platforms_router)  # type: ignore

    def test_create_platform(
        self,
    ) -> None:
        response = self.client.post(
            "/",
            json={
                "name": "PlayStation 5",
                "slug": "ps5",
            },  # type: ignore
            headers={"X-API-Key": self.api_key},
        )
        self.assertEqual(response.status_code, 201)
        data = response.json()
        self.assertEqual(data["name"], "PlayStation 5")
        self.assertEqual(data["slug"], "ps5")
        self.assertIsNotNone(data.get("id"))
        self.assertEqual(len(data["id"]), 8)

    def test_create_platform_custom_id(
        self,
    ) -> None:
        response = self.client.post(
            "/",
            json={
                "id": "xbox360",
                "name": "Xbox 360",
                "slug": "xbox-360",
            },  # type: ignore
            headers={"X-API-Key": self.api_key},
        )
        self.assertEqual(response.status_code, 201)
        data = response.json()
        self.assertEqual(data["id"], "xbox360")

    def test_create_platform_duplicate(
        self,
    ) -> None:
        response = self.client.post(
            "/",
            json={
                "id": "pc",
                "name": "Another PC",
                "slug": "another-pc",
            },  # type: ignore
            headers={"X-API-Key": self.api_key},
        )
        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertEqual(data["error"], "ID Already Exists")

    def test_update_platform(
        self,
    ) -> None:
        response = self.client.put(
            "/pc",
            json={"name": "Personal Computer"},  # type: ignore
            headers={"X-API-Key": self.api_key},
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["id"], "pc")
        self.assertEqual(data["name"], "Personal Computer")

    def test_delete_platform(
        self,
    ) -> None:
        Platforms.objects.create(id="todelete", name="To Delete", slug="to-delete")

        response = self.client.delete(
            "/todelete",
            headers={"X-API-Key": self.api_key},
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("deleted successfully", data["message"])
        self.assertFalse(Platforms.objects.filter(id="todelete").exists())
