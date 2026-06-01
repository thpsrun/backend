from __future__ import annotations

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import Client, TestCase
from nav.models import NavItem, SocialLink

ITEMS_URL = "/api/v1/auth/admin/navbar/items"
ITEMS_REORDER_URL = "/api/v1/auth/admin/navbar/items/reorder"
SOCIAL_REORDER_URL = "/api/v1/auth/admin/navbar/social/reorder"


class NavbarAdminTestBase(TestCase):
    def setUp(
        self,
    ) -> None:
        User = get_user_model()
        self.admin = User.objects.create_user(  # type: ignore
            username="navadmin",
            email="navadmin@example.com",
            password="supersecret123",
            is_superuser=True,
            is_staff=True,
        )
        self.client = Client()
        self.client.force_login(self.admin)


class NavReorderRoutingTest(NavbarAdminTestBase):
    """Regression tests for the 405 route-shadowing bug.

    These POST through the Django test client (full URL resolution), which is
    what surfaces the shadowing; calling the service directly would not.
    """

    def test_reorder_root_items_returns_204(
        self,
    ) -> None:
        # Mirrors the originally reported request: parent_id null, root reorder.
        rankings = NavItem.objects.create(name="Rankings", order=2)
        games = NavItem.objects.create(name="Games", order=1)

        response = self.client.post(
            ITEMS_REORDER_URL,
            data={"parent_id": None, "ordered_ids": [rankings.pk, games.pk]},
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 204)
        rankings.refresh_from_db()
        games.refresh_from_db()
        self.assertEqual(rankings.order, 1)
        self.assertEqual(games.order, 2)

    def test_reorder_child_items_returns_204(
        self,
    ) -> None:
        parent = NavItem.objects.create(name="Games")
        first = NavItem.objects.create(name="THPS1", parent=parent, order=1)
        second = NavItem.objects.create(name="THPS2", parent=parent, order=2)

        response = self.client.post(
            ITEMS_REORDER_URL,
            data={"parent_id": parent.pk, "ordered_ids": [second.pk, first.pk]},
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 204)
        first.refresh_from_db()
        second.refresh_from_db()
        self.assertEqual(second.order, 1)
        self.assertEqual(first.order, 2)

    def test_social_reorder_returns_204(
        self,
    ) -> None:
        discord = SocialLink.objects.create(
            platform="Discord",
            url="https://discord.gg/thps",
            order=1,
        )
        twitch = SocialLink.objects.create(
            platform="Twitch",
            url="https://twitch.tv/thps",
            order=2,
        )

        response = self.client.post(
            SOCIAL_REORDER_URL,
            data={"ordered_ids": [twitch.pk, discord.pk]},
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 204)
        discord.refresh_from_db()
        twitch.refresh_from_db()
        self.assertEqual(twitch.order, 1)
        self.assertEqual(discord.order, 2)

    def test_patch_non_integer_id_returns_404(
        self,
    ) -> None:
        # The {int:item_id} converter must not match a non-numeric segment, so
        # the request falls through to a 404 rather than hitting a real handler.
        response = self.client.patch(
            f"{ITEMS_URL}/not-a-number",
            data={"name": "x"},
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 404)


class NavDepthLimitTest(NavbarAdminTestBase):
    def _create_item(
        self,
        name: str,
        parent_id: int | None,
    ):
        return self.client.post(
            ITEMS_URL,
            data={"name": name, "parent_id": parent_id},
            content_type="application/json",
        )

    def test_depth_5_chain_allowed(
        self,
    ) -> None:
        parent_id: int | None = None
        for level in range(1, 6):
            response = self._create_item(f"L{level}", parent_id)
            self.assertEqual(
                response.status_code,
                201,
                response.content,
            )
            parent_id = response.json()["id"]

    def test_depth_6_rejected(
        self,
    ) -> None:
        parent_id: int | None = None
        for level in range(1, 6):
            response = self._create_item(f"L{level}", parent_id)
            self.assertEqual(
                response.status_code,
                201,
                response.content,
            )
            parent_id = response.json()["id"]

        response = self._create_item("L6", parent_id)
        self.assertEqual(response.status_code, 400)
        self.assertIn("5-level", response.content.decode())


class NavCleanDepthTest(TestCase):
    """Model-level clean() depth enforcement, independent of the API layer."""

    def _build_chain(
        self,
        tiers: int,
    ) -> NavItem:
        parent: NavItem | None = None
        item: NavItem | None = None
        for level in range(tiers):
            item = NavItem.objects.create(name=f"L{level}", parent=parent)
            parent = item
        assert item is not None
        return item

    def test_clean_allows_depth_5(
        self,
    ) -> None:
        deepest = self._build_chain(5)
        deepest.full_clean(exclude=("parent",))

    def test_clean_rejects_depth_6(
        self,
    ) -> None:
        deepest = self._build_chain(5)
        sixth = NavItem(name="L6", parent=deepest)
        with self.assertRaises(ValidationError):
            sixth.full_clean(exclude=("parent",))
