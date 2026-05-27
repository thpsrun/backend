from unittest.mock import patch

from accounts.turnstile import TurnstileUnavailable, verify_turnstile
from django.test import TestCase, override_settings


@override_settings(
    TURNSTILE_SECRET_KEY="test-secret",
    TURNSTILE_VERIFY_URL="https://example.invalid/siteverify",
    TURNSTILE_TIMEOUT_SECONDS=5,
)
class VerifyTurnstileTests(TestCase):
    def test_returns_true_when_cloudflare_reports_success(
        self,
    ) -> None:
        with patch("accounts.turnstile.requests.post") as mock_post:
            mock_post.return_value.status_code = 200
            mock_post.return_value.json.return_value = {"success": True}

            result = verify_turnstile("token-abc", "203.0.113.5")

        self.assertTrue(result)
        mock_post.assert_called_once_with(
            "https://example.invalid/siteverify",
            data={
                "secret": "test-secret",
                "response": "token-abc",
                "remoteip": "203.0.113.5",
            },
            timeout=5,
        )

    def test_returns_false_when_cloudflare_reports_failure(
        self,
    ) -> None:
        with patch("accounts.turnstile.requests.post") as mock_post:
            mock_post.return_value.status_code = 200
            mock_post.return_value.json.return_value = {
                "success": False,
                "error-codes": ["invalid-input-response"],
            }

            result = verify_turnstile("bad-token", None)

        self.assertFalse(result)

    def test_omits_remoteip_when_none(
        self,
    ) -> None:
        with patch("accounts.turnstile.requests.post") as mock_post:
            mock_post.return_value.status_code = 200
            mock_post.return_value.json.return_value = {"success": True}

            verify_turnstile("token-abc", None)

        mock_post.assert_called_once_with(
            "https://example.invalid/siteverify",
            data={
                "secret": "test-secret",
                "response": "token-abc",
            },
            timeout=5,
        )

    def test_raises_unavailable_on_request_exception(
        self,
    ) -> None:
        with patch("accounts.turnstile.requests.post") as mock_post:
            import requests as _requests

            mock_post.side_effect = _requests.Timeout("boom")

            with self.assertRaises(TurnstileUnavailable):
                verify_turnstile("token-abc", "203.0.113.5")

    def test_raises_unavailable_on_non_200(
        self,
    ) -> None:
        with patch("accounts.turnstile.requests.post") as mock_post:
            mock_post.return_value.status_code = 503

            with self.assertRaises(TurnstileUnavailable):
                verify_turnstile("token-abc", None)

    def test_raises_unavailable_on_invalid_json(
        self,
    ) -> None:
        with patch("accounts.turnstile.requests.post") as mock_post:
            mock_post.return_value.status_code = 200
            mock_post.return_value.json.side_effect = ValueError("nope")

            with self.assertRaises(TurnstileUnavailable):
                verify_turnstile("token-abc", None)


@override_settings(
    DEBUG=False,
    TURNSTILE_SECRET_KEY="test-secret",
    TURNSTILE_VERIFY_URL="https://example.invalid/siteverify",
    TURNSTILE_TIMEOUT_SECONDS=5,
)
class TurnstileMiddlewareTests(TestCase):
    PROTECTED_POST = "/_allauth/browser/v1/auth/login"

    def test_rejects_when_header_missing(
        self,
    ) -> None:
        response = self.client.post(
            self.PROTECTED_POST,
            data={},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 403)
        body = response.json()
        self.assertEqual(body["errors"][0]["code"], "turnstile_required")

    def test_rejects_when_verifier_returns_false(
        self,
    ) -> None:
        with patch(
            "accounts.middleware.verify_turnstile",
            return_value=False,
        ):
            response = self.client.post(
                self.PROTECTED_POST,
                data={},
                content_type="application/json",
                HTTP_X_TURNSTILE_TOKEN="bad",
            )
        self.assertEqual(response.status_code, 403)
        self.assertEqual(
            response.json()["errors"][0]["code"],
            "turnstile_failed",
        )

    def test_rejects_when_verifier_raises_unavailable(
        self,
    ) -> None:
        with patch(
            "accounts.middleware.verify_turnstile",
            side_effect=TurnstileUnavailable("boom"),
        ):
            response = self.client.post(
                self.PROTECTED_POST,
                data={},
                content_type="application/json",
                HTTP_X_TURNSTILE_TOKEN="any",
            )
        self.assertEqual(response.status_code, 403)
        self.assertEqual(
            response.json()["errors"][0]["code"],
            "turnstile_unavailable",
        )

    def test_passes_through_when_verifier_returns_true(
        self,
    ) -> None:
        with patch(
            "accounts.middleware.verify_turnstile",
            return_value=True,
        ):
            response = self.client.post(
                self.PROTECTED_POST,
                data={},
                content_type="application/json",
                HTTP_X_TURNSTILE_TOKEN="good",
            )
        # allauth responds with its own status (e.g. 400 for an empty body). The middleware
        # itself is satisfied as long as we did not get its own 403 + body.
        self.assertNotEqual(response.status_code, 403)

    def test_unprotected_path_passes_through_without_header(
        self,
    ) -> None:
        response = self.client.get("/api/v1/docs")
        self.assertNotEqual(response.status_code, 403)

    def test_each_protected_endpoint_is_gated(
        self,
    ) -> None:
        cases = [
            ("POST", "/_allauth/browser/v1/auth/login"),
            ("POST", "/_allauth/browser/v1/auth/password/request"),
            ("POST", "/_allauth/browser/v1/auth/provider/signup"),
            ("GET", "/_allauth/browser/v1/auth/provider/redirect"),
            ("POST", "/_allauth/browser/v1/auth/provider/redirect"),
        ]
        for method, path in cases:
            with self.subTest(method=method, path=path):
                if method == "POST":
                    response = self.client.post(
                        path,
                        data={},
                        content_type="application/json",
                    )
                else:
                    response = self.client.get(path)
                self.assertEqual(response.status_code, 403)
                self.assertEqual(
                    response.json()["errors"][0]["code"],
                    "turnstile_required",
                )


@override_settings(
    DEBUG=True,
    TURNSTILE_SECRET_KEY="test-secret",
)
class TurnstileMiddlewareDebugStillRunsTests(TestCase):
    def test_runs_even_when_debug_true(
        self,
    ) -> None:
        response = self.client.post(
            "/_allauth/browser/v1/auth/login",
            data={},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 403)
        self.assertEqual(
            response.json()["errors"][0]["code"],
            "turnstile_required",
        )


@override_settings(
    DEBUG=False,
    TURNSTILE_SECRET_KEY="",
)
class TurnstileMiddlewareSkipUnconfiguredTests(TestCase):
    def test_skip_when_secret_unset(
        self,
    ) -> None:
        response = self.client.post(
            "/_allauth/browser/v1/auth/login",
            data={},
            content_type="application/json",
        )
        self.assertNotEqual(response.status_code, 403)
