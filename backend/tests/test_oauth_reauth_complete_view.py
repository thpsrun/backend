from accounts.oauth_reauth import REAUTH_INTENT_SESSION_KEY
from django.test import TestCase, override_settings


@override_settings(FRONTEND_URL="https://example.test")
class OAuthReauthCompleteViewTests(TestCase):
    def test_renders_ok_status_and_origin(self) -> None:
        resp = self.client.get("/accounts/oauth-reauth-complete/?status=ok")
        self.assertEqual(resp.status_code, 200)
        body = resp.content.decode()
        self.assertIn('"oauth_reauth"', body)
        self.assertIn('"ok"', body)
        self.assertIn("https://example.test", body)
        self.assertIn("window.close", body)

    def test_renders_error_status_and_reason(self) -> None:
        resp = self.client.get(
            "/accounts/oauth-reauth-complete/?status=error&reason=account_mismatch",
        )
        self.assertEqual(resp.status_code, 200)
        body = resp.content.decode()
        self.assertIn('"error"', body)
        self.assertIn('"account_mismatch"', body)

    def test_unknown_status_defaults_to_error(self) -> None:
        resp = self.client.get("/accounts/oauth-reauth-complete/")
        self.assertEqual(resp.status_code, 200)
        body = resp.content.decode()
        self.assertIn('"error"', body)

    def test_status_is_whitelisted(self) -> None:
        resp = self.client.get(
            "/accounts/oauth-reauth-complete/?status=javascript:alert(1)",
        )
        self.assertEqual(resp.status_code, 200)
        body = resp.content.decode()
        self.assertNotIn("javascript:alert(1)", body)


@override_settings(FRONTEND_URL="https://example.test")
class OAuthReauthCancelTests(TestCase):
    def test_cancel_with_intent_redirects_to_complete_cancelled(self) -> None:
        session = self.client.session
        session[REAUTH_INTENT_SESSION_KEY] = {
            "provider": "discord",
            "user_id": 1,
            "social_account_id": 1,
            "created_at": "2099-01-01T00:00:00+00:00",
        }
        session.save()
        resp = self.client.get("/accounts/social/login/cancelled/")
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/accounts/oauth-reauth-complete/", resp["Location"])
        self.assertIn("status=cancelled", resp["Location"])
        self.assertNotIn(REAUTH_INTENT_SESSION_KEY, self.client.session)

    def test_cancel_without_intent_redirects_to_frontend(self) -> None:
        resp = self.client.get("/accounts/social/login/cancelled/")
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/login/cancelled/", resp["Location"])
        self.assertNotIn("/accounts/oauth-reauth-complete/", resp["Location"])

    def test_error_with_intent_redirects_to_complete_error(self) -> None:
        session = self.client.session
        session[REAUTH_INTENT_SESSION_KEY] = {
            "provider": "discord",
            "user_id": 1,
            "social_account_id": 1,
            "created_at": "2099-01-01T00:00:00+00:00",
        }
        session.save()
        resp = self.client.get("/accounts/social/login/error/")
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/accounts/oauth-reauth-complete/", resp["Location"])
        self.assertIn("status=error", resp["Location"])
        self.assertIn("reason=provider_error", resp["Location"])

    def test_error_without_intent_redirects_to_frontend(self) -> None:
        resp = self.client.get("/accounts/social/login/error/")
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/login/error/", resp["Location"])
        self.assertNotIn("/accounts/oauth-reauth-complete/", resp["Location"])
