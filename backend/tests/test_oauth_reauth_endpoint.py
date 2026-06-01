import time
from urllib.parse import parse_qs, urlparse

from accounts.oauth_reauth import REAUTH_INTENT_SESSION_KEY
from allauth.account.internal.flows.login import AUTHENTICATION_METHODS_SESSION_KEY
from allauth.socialaccount.models import SocialAccount
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import Client, TestCase
from srl.models.players import Players

User = get_user_model()


class InitiateOAuthReauthTests(TestCase):
    def setUp(self) -> None:
        super().setUp()
        cache.clear()
        self.user = User.objects.create_user(  # type: ignore
            username="reauthuser",
            email="r@x.test",
            password="supersecret123",
        )
        Players.objects.create(
            id="reauthuser",
            name="reauthuser",
            claim_status=Players.ClaimStatus.CLAIMED,
            user=self.user,
        )
        self.sa = SocialAccount.objects.create(
            user=self.user,
            provider="discord",
            uid="discord-uid-123",
            extra_data={"username": "reauthuser"},
        )
        self.client = Client()

    def tearDown(self) -> None:
        cache.clear()
        super().tearDown()

    def test_returns_authorize_url_and_stores_intent(self) -> None:
        self.client.force_login(self.user)
        url = "/api/v1/auth/me/auth/reauthenticate/oauth/discord"
        resp = self.client.post(url)
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertIn("authorize_url", body)
        parsed = urlparse(body["authorize_url"])
        self.assertEqual(parsed.scheme, "https")
        self.assertEqual(parsed.netloc, "discord.com")
        self.assertEqual(parsed.path, "/api/oauth2/authorize")
        params = parse_qs(parsed.query)
        self.assertEqual(params.get("response_type"), ["code"])
        self.assertIn("state", params)
        self.assertIn("client_id", params)
        intent = self.client.session[REAUTH_INTENT_SESSION_KEY]
        self.assertEqual(intent["provider"], "discord")
        self.assertEqual(intent["user_id"], self.user.pk)
        self.assertEqual(intent["social_account_id"], self.sa.pk)

    def test_404_when_provider_not_linked(self) -> None:
        self.client.force_login(self.user)
        url = "/api/v1/auth/me/auth/reauthenticate/oauth/twitch"
        resp = self.client.post(url)
        self.assertEqual(resp.status_code, 404)
        self.assertEqual(resp.json()["error"], "no_social_account")
        self.assertNotIn(REAUTH_INTENT_SESSION_KEY, self.client.session)

    def test_400_for_unsupported_provider(self) -> None:
        self.client.force_login(self.user)
        url = "/api/v1/auth/me/auth/reauthenticate/oauth/notarealprovider"
        resp = self.client.post(url)
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.json()["error"], "unsupported_provider")

    def test_requires_authentication(self) -> None:
        url = "/api/v1/auth/me/auth/reauthenticate/oauth/discord"
        resp = self.client.post(url)
        self.assertIn(resp.status_code, (401, 403))


class RateLimitTests(TestCase):
    def setUp(self) -> None:
        cache.clear()
        self.user = User.objects.create_user(  # type: ignore
            username="rl",
            email="rl@x.test",
            password="supersecret123",
        )
        Players.objects.create(
            id="rl",
            name="rl",
            claim_status=Players.ClaimStatus.CLAIMED,
            user=self.user,
        )
        SocialAccount.objects.create(
            user=self.user,
            provider="discord",
            uid="rl-uid",
        )
        self.client = Client()

    def tearDown(self) -> None:
        cache.clear()

    def test_sixth_call_in_a_minute_is_429(self) -> None:
        self.client.force_login(self.user)
        url = "/api/v1/auth/me/auth/reauthenticate/oauth/discord"
        for _ in range(5):
            self.assertEqual(self.client.post(url).status_code, 200)
        self.assertEqual(self.client.post(url).status_code, 429)


class EndToEndDisconnectTests(TestCase):
    def setUp(self) -> None:
        cache.clear()
        self.user = User.objects.create_user(  # type: ignore
            username="e2e",
            email="e2e@x.test",
            password="e2e-password",
        )
        Players.objects.create(
            id="e2e",
            name="e2e",
            claim_status=Players.ClaimStatus.CLAIMED,
            user=self.user,
        )
        self.discord = SocialAccount.objects.create(
            user=self.user,
            provider="discord",
            uid="e2e-discord",
        )
        self.twitch = SocialAccount.objects.create(
            user=self.user,
            provider="twitch",
            uid="e2e-twitch",
        )
        self.client = Client()

    def tearDown(self) -> None:
        cache.clear()

    def test_disconnect_succeeds_after_oauth_reauth_stamps_recent_auth(self) -> None:
        self.client.force_login(self.user)
        resp = self.client.delete("/api/v1/auth/me/auth/social-accounts/discord")
        self.assertEqual(resp.status_code, 401)
        self.assertEqual(resp.json()["error"], "reauth_required")

        session = self.client.session
        session[AUTHENTICATION_METHODS_SESSION_KEY] = [
            {
                "method": "socialaccount",
                "at": time.time(),
                "provider": "discord",
                "uid": "e2e-discord",
                "reauthenticated": True,
            },
        ]
        session.save()

        # Disconnect now succeeds.
        resp = self.client.delete("/api/v1/auth/me/auth/social-accounts/discord")
        self.assertEqual(resp.status_code, 204)
        self.assertFalse(
            SocialAccount.objects.filter(
                user=self.user,
                provider="discord",
            ).exists(),
        )
