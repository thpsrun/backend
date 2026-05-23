from __future__ import annotations

from api.models import APIKey, APIKeyRevokedReason
from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings
from srl.models.games import Games
from srl.models.players import Players


def _make_game(
    game_id: str,
) -> Games:
    return Games.objects.create(
        id=game_id,
        name=game_id,
        slug=game_id,
        twitch=game_id,
        release="2000-01-01",
        boxart=f"https://example.com/{game_id}.png",
        defaulttime="rta",
        idefaulttime="rta",
        pointsmax=1000,
        ipointsmax=100,
    )


class APIKeyEndpointsTestBase(TestCase):

    @classmethod
    def setUpTestData(
        cls,
    ) -> None:
        cls.game = _make_game("apikg1")

    def setUp(
        self,
    ) -> None:
        User = get_user_model()
        self.user = User.objects.create_user(  # type: ignore
            username="alice",
            email="alice@example.com",
            password="supersecret123",
        )
        self.client = Client()


class ListAPIKeysTest(APIKeyEndpointsTestBase):

    def test_list_empty(
        self,
    ) -> None:
        self.client.force_login(self.user)
        response = self.client.get("/api/v1/auth/me/api-keys")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), [])

    def test_list_own_only(
        self,
    ) -> None:
        User = get_user_model()
        bob = User.objects.create_user(  # type: ignore
            username="bob",
            email="bob@example.com",
            password="supersecret123",
        )
        APIKey.objects.create_key(user=bob, label="bob's key")
        APIKey.objects.create_key(user=self.user, label="alice's key")

        self.client.force_login(self.user)
        response = self.client.get("/api/v1/auth/me/api-keys")

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(len(body), 1)
        self.assertEqual(body[0]["label"], "alice's key")

    def test_list_requires_auth(
        self,
    ) -> None:
        response = self.client.get("/api/v1/auth/me/api-keys")
        self.assertEqual(response.status_code, 401)


class GetAPIKeyTest(APIKeyEndpointsTestBase):

    def test_get_own_key(
        self,
    ) -> None:
        key, _ = APIKey.objects.create_key(user=self.user, label="one")

        self.client.force_login(self.user)
        response = self.client.get(f"/api/v1/auth/me/api-keys/{key.pk}")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["label"], "one")

    def test_get_other_users_key_returns_404(
        self,
    ) -> None:
        User = get_user_model()
        bob = User.objects.create_user(  # type: ignore
            username="bob",
            email="bob@example.com",
            password="supersecret123",
        )
        bob_key, _ = APIKey.objects.create_key(user=bob, label="bob's")

        self.client.force_login(self.user)
        response = self.client.get(f"/api/v1/auth/me/api-keys/{bob_key.pk}")

        self.assertEqual(response.status_code, 404)


class CreateAPIKeyTest(APIKeyEndpointsTestBase):

    def test_create_key_basic(
        self,
    ) -> None:
        self.client.force_login(self.user)
        response = self.client.post(
            "/api/v1/auth/me/api-keys",
            data={"label": "test key", "expiry_days": 180},
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 201)
        body = response.json()
        self.assertEqual(body["label"], "test key")
        self.assertIn("key", body)
        self.assertTrue(body["key"])
        self.assertEqual(APIKey.objects.filter(user=self.user).count(), 1)

    def test_create_key_with_invalid_expiry_returns_422(
        self,
    ) -> None:
        self.client.force_login(self.user)
        response = self.client.post(
            "/api/v1/auth/me/api-keys",
            data={"label": "bad", "expiry_days": 7},
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 422)

    @override_settings(API_KEY_MAX_PER_USER=2)
    def test_create_key_enforces_max_per_user(
        self,
    ) -> None:
        self.client.force_login(self.user)
        for i in range(2):
            response = self.client.post(
                "/api/v1/auth/me/api-keys",
                data={"label": f"k{i}", "expiry_days": 180},
                content_type="application/json",
            )
            self.assertEqual(response.status_code, 201)

        response = self.client.post(
            "/api/v1/auth/me/api-keys",
            data={"label": "overflow", "expiry_days": 180},
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("max", response.json().get("detail", "").lower())

    def test_create_key_rejects_unknown_capability(
        self,
    ) -> None:
        self.client.force_login(self.user)
        response = self.client.post(
            "/api/v1/auth/me/api-keys",
            data={
                "label": "bad",
                "expiry_days": 180,
                "scope_capabilities": ["made.up"],
            },
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("unknown capability", response.json()["detail"].lower())

    def test_create_key_rejects_capability_user_lacks(
        self,
    ) -> None:
        """Regular user cannot scope a capability they cannot exercise anywhere."""
        self.client.force_login(self.user)
        response = self.client.post(
            "/api/v1/auth/me/api-keys",
            data={
                "label": "admin-cap",
                "expiry_days": 180,
                "scope_capabilities": ["users.admin"],
            },
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400)

    def test_create_key_rejects_unknown_game(
        self,
    ) -> None:
        self.client.force_login(self.user)
        response = self.client.post(
            "/api/v1/auth/me/api-keys",
            data={
                "label": "with-game",
                "expiry_days": 180,
                "scope_games": ["nonexistent-game"],
            },
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("unknown games", response.json()["detail"].lower())

    def test_create_key_with_game_scope_for_superuser(
        self,
    ) -> None:
        User = get_user_model()
        admin = User.objects.create_user(  # type: ignore
            username="admin",
            email="admin@example.com",
            password="supersecret123",
            is_superuser=True,
        )
        self.client.force_login(admin)

        response = self.client.post(
            "/api/v1/auth/me/api-keys",
            data={
                "label": "admin-scoped",
                "expiry_days": 180,
                "scope_capabilities": ["games.manage"],
                "scope_games": [self.game.pk],
            },
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 201)
        body = response.json()
        self.assertEqual(body["scope_capabilities"], ["games.manage"])
        self.assertEqual(body["scope_games"], [self.game.pk])


class APIKeySubsetEnforcementTest(APIKeyEndpointsTestBase):
    """Covers _enforce_subset_of_presenting_key: a narrow key must not be
    usable to mint a broader key. With validation order (subset -> user-scope),
    these cases return 403, not 400.
    """

    def test_narrow_key_cannot_reach_create_endpoint(
        self,
    ) -> None:
        # Key scoped to runs.submit only; does not admit api_keys.create_own.
        # The authed() dependency itself 403s before my subset check runs.
        _, raw = APIKey.objects.create_key(
            user=self.user,
            label="narrow",
            scope_capabilities=["runs.submit"],
        )

        response = self.client.post(
            "/api/v1/auth/me/api-keys",
            data={
                "label": "broader",
                "expiry_days": 180,
                "scope_capabilities": ["runs.verify"],
            },
            content_type="application/json",
            HTTP_X_API_KEY=raw,
        )

        self.assertEqual(response.status_code, 403)

    def test_capability_scoped_presenter_rejects_broader_new_key(
        self,
    ) -> None:
        """Presenter has api_keys.create_own + runs.submit; new key asks for
        runs.verify which is outside the presenter's scope_capabilities. The
        subset check runs before _enforce_user_can_scope, so the presenter's
        non-mod status never gets tested here; making self.user a mod just
        keeps the test focused on the subset logic in case ordering ever
        changes.
        """
        player = Players.objects.create(
            id="alicemod1",
            name="alice",
            claim_status=Players.ClaimStatus.CLAIMED,
            user=self.user,
        )
        self.game.moderators.add(player)

        _, raw = APIKey.objects.create_key(
            user=self.user,
            label="scoped-create-key",
            scope_capabilities=["api_keys.create_own", "runs.submit"],
        )

        response = self.client.post(
            "/api/v1/auth/me/api-keys",
            data={
                "label": "broader",
                "expiry_days": 180,
                "scope_capabilities": ["runs.verify"],
            },
            content_type="application/json",
            HTTP_X_API_KEY=raw,
        )

        self.assertEqual(response.status_code, 403)
        self.assertIn(
            "presenting api key scope does not include",
            response.json()["detail"].lower(),
        )

    def test_capability_scoped_presenter_rejects_unrestricted_new_key(
        self,
    ) -> None:
        """Presenter has caps; new key has empty caps (= unrestricted).
        Broader is never allowed.
        """
        _, raw = APIKey.objects.create_key(
            user=self.user,
            label="scoped",
            scope_capabilities=["api_keys.create_own"],
        )

        response = self.client.post(
            "/api/v1/auth/me/api-keys",
            data={"label": "broader", "expiry_days": 180},
            content_type="application/json",
            HTTP_X_API_KEY=raw,
        )

        self.assertEqual(response.status_code, 403)

    def test_game_scoped_presenter_rejects_unrestricted_new_key(
        self,
    ) -> None:
        """Presenter is restricted to one game; new key must also list games."""
        User = get_user_model()
        admin = User.objects.create_user(  # type: ignore
            username="gadmin",
            email="gadmin@example.com",
            password="supersecret123",
            is_superuser=True,
        )
        presenting_key, raw = APIKey.objects.create_key(
            user=admin,
            label="game-scoped",
            scope_capabilities=["api_keys.create_own", "games.manage"],
        )
        presenting_key.scope_games.add(self.game)

        response = self.client.post(
            "/api/v1/auth/me/api-keys",
            data={
                "label": "no-games",
                "expiry_days": 180,
                "scope_capabilities": ["games.manage"],
            },
            content_type="application/json",
            HTTP_X_API_KEY=raw,
        )

        self.assertEqual(response.status_code, 403)


class PatchAPIKeyTest(APIKeyEndpointsTestBase):

    def test_patch_label(
        self,
    ) -> None:
        key, _ = APIKey.objects.create_key(user=self.user, label="old")

        self.client.force_login(self.user)
        response = self.client.patch(
            f"/api/v1/auth/me/api-keys/{key.pk}",
            data={"label": "new"},
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        key.refresh_from_db()
        self.assertEqual(key.label, "new")

    def test_patch_description(
        self,
    ) -> None:
        key, _ = APIKey.objects.create_key(user=self.user, label="x")

        self.client.force_login(self.user)
        response = self.client.patch(
            f"/api/v1/auth/me/api-keys/{key.pk}",
            data={"description": "new desc"},
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        key.refresh_from_db()
        self.assertEqual(key.description, "new desc")

    def test_patch_other_users_key_returns_404(
        self,
    ) -> None:
        User = get_user_model()
        bob = User.objects.create_user(  # type: ignore
            username="bob",
            email="bob@example.com",
            password="supersecret123",
        )
        bob_key, _ = APIKey.objects.create_key(user=bob, label="bob's")

        self.client.force_login(self.user)
        response = self.client.patch(
            f"/api/v1/auth/me/api-keys/{bob_key.pk}",
            data={"label": "hacked"},
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 404)


class RevokeAPIKeyTest(APIKeyEndpointsTestBase):

    def test_revoke_own(
        self,
    ) -> None:
        key, _ = APIKey.objects.create_key(user=self.user, label="x")
        self.assertIsNone(key.revoked_at)

        self.client.force_login(self.user)
        response = self.client.delete(f"/api/v1/auth/me/api-keys/{key.pk}")

        self.assertEqual(response.status_code, 204)
        key.refresh_from_db()
        self.assertTrue(key.revoked)
        self.assertEqual(key.revoked_reason, APIKeyRevokedReason.USER)
        self.assertIsNotNone(key.revoked_at)

    def test_revoke_already_revoked_is_idempotent(
        self,
    ) -> None:
        key, _ = APIKey.objects.create_key(user=self.user, label="x")
        key.revoke(APIKeyRevokedReason.USER)
        first_revoked_at = key.revoked_at

        self.client.force_login(self.user)
        response = self.client.delete(f"/api/v1/auth/me/api-keys/{key.pk}")

        self.assertEqual(response.status_code, 204)
        key.refresh_from_db()
        self.assertTrue(key.revoked)
        self.assertEqual(key.revoked_reason, APIKeyRevokedReason.USER)
        # Timestamp must not be overwritten on a no-op revoke.
        self.assertEqual(key.revoked_at, first_revoked_at)

    def test_revoke_other_users_key_returns_404(
        self,
    ) -> None:
        User = get_user_model()
        bob = User.objects.create_user(  # type: ignore
            username="bob",
            email="bob@example.com",
            password="supersecret123",
        )
        bob_key, _ = APIKey.objects.create_key(user=bob, label="bob's")

        self.client.force_login(self.user)
        response = self.client.delete(f"/api/v1/auth/me/api-keys/{bob_key.pk}")

        self.assertEqual(response.status_code, 404)


class MyCapabilitiesTest(APIKeyEndpointsTestBase):

    def test_anonymous_is_unauthorized(
        self,
    ) -> None:
        response = self.client.get("/api/v1/auth/me/capabilities")
        self.assertEqual(response.status_code, 401)

    def test_plain_user_sees_non_scoped_caps_only(
        self,
    ) -> None:
        self.client.force_login(self.user)
        response = self.client.get("/api/v1/auth/me/capabilities")

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertIn("api_keys.create_own", body["capabilities"])
        self.assertIn("api_keys.list_own", body["capabilities"])
        self.assertNotIn("runs.submit", body["capabilities"])
        self.assertNotIn("users.admin", body["capabilities"])
        self.assertEqual(body["games"], [])

    def test_claimed_player_gets_player_scopes(
        self,
    ) -> None:
        Players.objects.create(
            id="alicecap1",
            name="alice",
            claim_status=Players.ClaimStatus.CLAIMED,
            user=self.user,
        )

        self.client.force_login(self.user)
        response = self.client.get("/api/v1/auth/me/capabilities")

        self.assertEqual(response.status_code, 200)
        caps = response.json()["capabilities"]
        self.assertIn("runs.submit", caps)
        self.assertIn("guides.create", caps)
        # profile.edit_own is session-only and intentionally not exposed in the scope picker.
        self.assertNotIn("profile.edit_own", caps)
        self.assertNotIn("users.admin", caps)
        self.assertNotIn("runs.verify", caps)

    def test_mod_gets_mod_scopes_and_game_listed(
        self,
    ) -> None:
        player = Players.objects.create(
            id="alicecap2",
            name="alice",
            claim_status=Players.ClaimStatus.CLAIMED,
            user=self.user,
        )
        self.game.moderators.add(player)

        self.client.force_login(self.user)
        response = self.client.get("/api/v1/auth/me/capabilities")

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertIn("runs.verify", body["capabilities"])
        self.assertIn("games.manage", body["capabilities"])
        self.assertNotIn("runs.delete", body["capabilities"])
        self.assertNotIn("users.admin", body["capabilities"])

        game_ids = [g["id"] for g in body["games"]]
        self.assertIn(self.game.pk, game_ids)

    def test_superuser_gets_all_scoped_caps_and_all_games(
        self,
    ) -> None:
        User = get_user_model()
        admin = User.objects.create_user(  # type: ignore
            username="admincap",
            email="admincap@example.com",
            password="supersecret123",
            is_superuser=True,
        )

        self.client.force_login(admin)
        response = self.client.get("/api/v1/auth/me/capabilities")

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertNotIn("users.admin", body["capabilities"])
        self.assertIn("runs.delete", body["capabilities"])
        self.assertIn("runs.verify", body["capabilities"])
        self.assertIn("games.manage", body["capabilities"])

        game_ids = [g["id"] for g in body["games"]]
        self.assertIn(self.game.pk, game_ids)


class AdminAPIKeyEndpointsTest(APIKeyEndpointsTestBase):

    def setUp(
        self,
    ) -> None:
        super().setUp()
        User = get_user_model()
        self.admin = User.objects.create_user(  # type: ignore
            username="adminuser",
            email="adminuser@example.com",
            password="supersecret123",
            is_superuser=True,
        )

    def test_admin_list_by_user(
        self,
    ) -> None:
        User = get_user_model()
        target = User.objects.create_user(  # type: ignore
            username="target",
            email="target@example.com",
            password="supersecret123",
        )
        target_key, _ = APIKey.objects.create_key(user=target, label="t1")
        APIKey.objects.create_key(user=self.admin, label="admin-own")

        self.client.force_login(self.admin)
        response = self.client.get(
            f"/api/v1/auth/admin/api-keys?user={target.pk}",
        )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(len(body), 1)
        self.assertEqual(body[0]["id"], str(target_key.pk))

    def test_admin_revoke(
        self,
    ) -> None:
        User = get_user_model()
        target = User.objects.create_user(  # type: ignore
            username="target",
            email="target@example.com",
            password="supersecret123",
        )
        target_key, _ = APIKey.objects.create_key(user=target, label="t1")

        self.client.force_login(self.admin)
        response = self.client.delete(
            f"/api/v1/auth/admin/api-keys/{target_key.pk}",
        )

        self.assertEqual(response.status_code, 204)
        target_key.refresh_from_db()
        self.assertTrue(target_key.revoked)
        self.assertEqual(target_key.revoked_reason, APIKeyRevokedReason.ADMIN)
        self.assertIsNotNone(target_key.revoked_at)

    def test_admin_revoke_nonexistent_returns_404(
        self,
    ) -> None:
        self.client.force_login(self.admin)
        response = self.client.delete(
            "/api/v1/auth/admin/api-keys/does-not-exist",
        )

        self.assertEqual(response.status_code, 404)

    def test_admin_list_unknown_user_returns_404(
        self,
    ) -> None:
        self.client.force_login(self.admin)
        response = self.client.get(
            "/api/v1/auth/admin/api-keys?user=99999999",
        )

        self.assertEqual(response.status_code, 404)
        self.assertIn("not found", response.json()["detail"].lower())

    def test_admin_endpoints_denied_for_regular_user(
        self,
    ) -> None:
        self.client.force_login(self.user)
        response = self.client.get(
            f"/api/v1/auth/admin/api-keys?user={self.user.pk}",
        )

        self.assertEqual(response.status_code, 403)


class APIKeyUsageTrackingTest(APIKeyEndpointsTestBase):
    """Covers the middleware that updates last_used/last_used_ip when an API
    key authenticates a request.
    """

    def test_last_used_populated_after_authed_request(
        self,
    ) -> None:
        key, raw = APIKey.objects.create_key(user=self.user, label="tracker")
        self.assertIsNone(key.last_used)
        self.assertIsNone(key.last_used_ip)

        response = self.client.get(
            "/api/v1/auth/me/api-keys",
            HTTP_X_API_KEY=raw,
            REMOTE_ADDR="203.0.113.42",
        )
        self.assertEqual(response.status_code, 200)

        key.refresh_from_db()
        self.assertIsNotNone(key.last_used)
        self.assertEqual(key.last_used_ip, "203.0.113.42")

    def test_last_used_not_updated_for_session_auth(
        self,
    ) -> None:
        """A session-authenticated request should not bump any api_key fields,
        since no key was presented. Guards against request.api_key leaking
        across requests or being mistakenly set on session auth.
        """
        key, _ = APIKey.objects.create_key(user=self.user, label="idle")

        self.client.force_login(self.user)
        response = self.client.get("/api/v1/auth/me/api-keys")
        self.assertEqual(response.status_code, 200)

        key.refresh_from_db()
        self.assertIsNone(key.last_used)
        self.assertIsNone(key.last_used_ip)
