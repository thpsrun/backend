from datetime import timedelta
from importlib import import_module

from accounts.oauth_reauth import (
    REAUTH_COMPLETE_URL_NAME,
    REAUTH_INTENT_SESSION_KEY,
    clear_intent,
    handle_reauth,
    read_intent,
    write_intent,
)
from allauth.account.internal.flows.login import AUTHENTICATION_METHODS_SESSION_KEY
from allauth.account.internal.flows.reauthentication import did_recently_authenticate
from allauth.core.exceptions import ImmediateHttpResponse
from allauth.socialaccount.models import SocialAccount, SocialLogin
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.test import RequestFactory, TestCase, override_settings
from django.utils import timezone

User = get_user_model()


def _fake_sociallogin(provider: str, uid: str) -> SocialLogin:
    sl = SocialLogin()
    sl.account = SocialAccount(provider=provider, uid=uid)
    return sl


class IntentHelperTests(TestCase):
    def setUp(self) -> None:
        engine = import_module(settings.SESSION_ENGINE)
        rf = RequestFactory()
        self.request = rf.post("/api/v1/auth/me/auth/reauthenticate/oauth/discord")
        self.request.session = engine.SessionStore()

    def test_write_then_read_round_trips(self) -> None:
        write_intent(
            self.request,
            provider="discord",
            user_id=7,
            social_account_id=42,
        )
        intent = read_intent(self.request)
        self.assertIsNotNone(intent)
        self.assertEqual(intent["provider"], "discord")
        self.assertEqual(intent["user_id"], 7)
        self.assertEqual(intent["social_account_id"], 42)
        self.assertIn("created_at", intent)

    def test_clear_removes_intent(self) -> None:
        write_intent(
            self.request,
            provider="discord",
            user_id=7,
            social_account_id=42,
        )
        clear_intent(self.request)
        self.assertNotIn(REAUTH_INTENT_SESSION_KEY, self.request.session)
        self.assertIsNone(read_intent(self.request))

    @override_settings(OAUTH_REAUTH_INTENT_TTL_SECONDS=600)
    def test_read_returns_none_when_expired(self) -> None:
        write_intent(
            self.request,
            provider="discord",
            user_id=7,
            social_account_id=42,
        )
        past = (timezone.now() - timedelta(seconds=601)).isoformat()
        self.request.session[REAUTH_INTENT_SESSION_KEY]["created_at"] = past
        self.assertIsNone(read_intent(self.request))
        # Expired intents are auto-cleared on read.
        self.assertNotIn(REAUTH_INTENT_SESSION_KEY, self.request.session)

    def test_read_returns_none_when_missing(self) -> None:
        self.assertIsNone(read_intent(self.request))


class HandleReauthTests(TestCase):
    def setUp(self) -> None:
        self.user = User.objects.create_user(username="ru", email="ru@x.test")
        self.sa = SocialAccount.objects.create(
            user=self.user,
            provider="discord",
            uid="real-uid",
        )
        rf = RequestFactory()
        self.request = rf.get("/accounts/discord/login/callback/")
        engine = import_module(settings.SESSION_ENGINE)
        self.request.session = engine.SessionStore()
        self.request.user = self.user
        write_intent(
            self.request,
            provider="discord",
            user_id=self.user.pk,
            social_account_id=self.sa.pk,
        )

    def _assert_redirects_to_complete(
        self,
        exc: ImmediateHttpResponse,
        status: str,
        reason: str = "",
    ) -> None:
        resp = exc.response
        self.assertEqual(resp.status_code, 302)
        self.assertIn(f"status={status}", resp["Location"])
        if reason:
            self.assertIn(f"reason={reason}", resp["Location"])

    def test_success_stamps_recent_auth_and_clears_intent(self) -> None:
        sl = _fake_sociallogin("discord", "real-uid")
        with self.assertRaises(ImmediateHttpResponse) as ctx:
            handle_reauth(self.request, sl, read_intent(self.request))
        self._assert_redirects_to_complete(ctx.exception, "ok")
        self.assertNotIn(REAUTH_INTENT_SESSION_KEY, self.request.session)
        methods = self.request.session[AUTHENTICATION_METHODS_SESSION_KEY]
        self.assertTrue(
            any(m.get("method") == "socialaccount" for m in methods),
        )
        self.assertTrue(did_recently_authenticate(self.request))

    def test_provider_mismatch_rejects(self) -> None:
        sl = _fake_sociallogin("twitch", "real-uid")
        with self.assertRaises(ImmediateHttpResponse) as ctx:
            handle_reauth(self.request, sl, read_intent(self.request))
        self._assert_redirects_to_complete(ctx.exception, "error", "provider_mismatch")
        self.assertNotIn(REAUTH_INTENT_SESSION_KEY, self.request.session)

    def test_account_uid_mismatch_rejects(self) -> None:
        sl = _fake_sociallogin("discord", "wrong-uid")
        with self.assertRaises(ImmediateHttpResponse) as ctx:
            handle_reauth(self.request, sl, read_intent(self.request))
        self._assert_redirects_to_complete(ctx.exception, "error", "account_mismatch")
        self.assertNotIn(REAUTH_INTENT_SESSION_KEY, self.request.session)

    def test_user_mismatch_rejects(self) -> None:
        other = User.objects.create_user(username="other", email="o@x.test")
        self.request.user = other
        sl = _fake_sociallogin("discord", "real-uid")
        with self.assertRaises(ImmediateHttpResponse) as ctx:
            handle_reauth(self.request, sl, read_intent(self.request))
        self._assert_redirects_to_complete(ctx.exception, "error", "user_mismatch")
        self.assertNotIn(REAUTH_INTENT_SESSION_KEY, self.request.session)

    def test_anonymous_user_rejects(self) -> None:
        self.request.user = AnonymousUser()
        sl = _fake_sociallogin("discord", "real-uid")
        with self.assertRaises(ImmediateHttpResponse) as ctx:
            handle_reauth(self.request, sl, read_intent(self.request))
        self._assert_redirects_to_complete(ctx.exception, "error", "not_authenticated")
        self.assertNotIn(REAUTH_INTENT_SESSION_KEY, self.request.session)

    def test_intent_pointing_to_deleted_account_rejects(self) -> None:
        self.sa.delete()
        sl = _fake_sociallogin("discord", "real-uid")
        with self.assertRaises(ImmediateHttpResponse) as ctx:
            handle_reauth(self.request, sl, read_intent(self.request))
        self._assert_redirects_to_complete(ctx.exception, "error", "account_mismatch")
        self.assertNotIn(REAUTH_INTENT_SESSION_KEY, self.request.session)

    def test_expired_intent_rejects(self) -> None:
        from datetime import timedelta as _td

        from django.utils import timezone as _tz

        past = (
            _tz.now() - _td(seconds=settings.OAUTH_REAUTH_INTENT_TTL_SECONDS + 60)
        ).isoformat()
        self.request.session[REAUTH_INTENT_SESSION_KEY]["created_at"] = past
        sl = _fake_sociallogin("discord", "real-uid")
        with self.assertRaises(ImmediateHttpResponse) as ctx:
            handle_reauth(
                self.request, sl, self.request.session[REAUTH_INTENT_SESSION_KEY]
            )
        self._assert_redirects_to_complete(ctx.exception, "error", "intent_expired")
        self.assertNotIn(REAUTH_INTENT_SESSION_KEY, self.request.session)

    def test_url_name_constant_exported(self) -> None:
        self.assertEqual(REAUTH_COMPLETE_URL_NAME, "oauth_reauth_complete")
