from __future__ import annotations

from unittest.mock import patch

from allauth.account.models import EmailAddress
from django.contrib.auth import get_user_model
from django.core import mail
from django.test import Client, TestCase, override_settings
from srl.models.players import Players


def _seed_eligible_player(
    src_user_id: str = "src-test-id",
) -> Players:
    return Players.objects.create(
        id=src_user_id,
        name="ada",
        url="",
        claim_status=Players.ClaimStatus.UNCLAIMED,
    )


class RegisterVerificationTest(TestCase):

    def setUp(
        self,
    ) -> None:
        self.player = _seed_eligible_player()
        self.client = Client()
        self._has_run_patch = patch(
            "api.v1.routers.auth.register.RunPlayers.objects",
        )
        mock_runs = self._has_run_patch.start()
        mock_runs.filter.return_value.exists.return_value = True
        self.addCleanup(self._has_run_patch.stop)

        self._src_patch = patch(
            "api.v1.routers.auth.register.http_requests.get",
        )
        mock_get = self._src_patch.start()
        mock_get.return_value.status_code = 200
        mock_get.return_value.json.return_value = {
            "data": {"id": self.player.id},
        }
        self.addCleanup(self._src_patch.stop)

    def test_register_returns_202_verification_required(
        self,
    ) -> None:
        response = self.client.post(
            "/api/v1/auth/register",
            data={
                "src_api_key": "irrelevant",
                "username": "ada",
                "email": "ada@example.com",
                "password1": "supersecret123",
                "password2": "supersecret123",
                "save_key": False,
            },
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 202)
        body = response.json()
        self.assertEqual(body["status"], "verification_required")
        self.assertEqual(body["email"], "ada@example.com")
        self.assertEqual(body["username"], "ada")
        self.assertEqual(body["src_user_id"], self.player.id)

    def test_register_does_not_log_in(
        self,
    ) -> None:
        self.client.post(
            "/api/v1/auth/register",
            data={
                "src_api_key": "irrelevant",
                "username": "ada",
                "email": "ada@example.com",
                "password1": "supersecret123",
                "password2": "supersecret123",
                "save_key": False,
            },
            content_type="application/json",
        )
        # No session cookie issued: hitting /me returns 401.
        me_response = self.client.get("/api/v1/auth/me")
        self.assertEqual(me_response.status_code, 401)

    def test_register_creates_unverified_email_address(
        self,
    ) -> None:
        self.client.post(
            "/api/v1/auth/register",
            data={
                "src_api_key": "irrelevant",
                "username": "ada",
                "email": "ada@example.com",
                "password1": "supersecret123",
                "password2": "supersecret123",
                "save_key": False,
            },
            content_type="application/json",
        )
        User = get_user_model()
        user = User.objects.get(username="ada")
        ea = EmailAddress.objects.get(user=user)
        self.assertEqual(ea.email, "ada@example.com")
        self.assertFalse(ea.verified)
        self.assertTrue(ea.primary)

    @override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
    def test_register_sends_confirmation_email(
        self,
    ) -> None:
        mail.outbox = []
        self.client.post(
            "/api/v1/auth/register",
            data={
                "src_api_key": "irrelevant",
                "username": "ada",
                "email": "ada@example.com",
                "password1": "supersecret123",
                "password2": "supersecret123",
                "save_key": False,
            },
            content_type="application/json",
        )
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ["ada@example.com"])


class CorrectEmailTest(TestCase):

    def setUp(
        self,
    ) -> None:
        User = get_user_model()
        self.player = _seed_eligible_player(src_user_id="src-correct-id")
        self.user = User.objects.create_user(  # type: ignore
            username="byron",
            email="byron-typo@example.com",
            password="supersecret123",
        )
        self.player.user = self.user
        self.player.claim_status = Players.ClaimStatus.CLAIMED
        self.player.save(update_fields=["user", "claim_status"])
        self.email_address = EmailAddress.objects.create(
            user=self.user,
            email=self.user.email,
            primary=True,
            verified=False,
        )
        self.client = Client()
        self._src_patch = patch(
            "api.v1.routers.auth.register.http_requests.get",
        )
        mock_get = self._src_patch.start()
        mock_get.return_value.status_code = 200
        mock_get.return_value.json.return_value = {
            "data": {"id": self.player.id},
        }
        self.addCleanup(self._src_patch.stop)

    @override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
    def test_correct_email_updates_address(
        self,
    ) -> None:
        mail.outbox = []
        response = self.client.post(
            "/api/v1/auth/register/correct-email",
            data={
                "src_api_key": "irrelevant",
                "new_email": "byron@example.com",
            },
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["status"], "verification_sent")
        self.assertEqual(body["email"], "byron@example.com")
        self.user.refresh_from_db()
        self.email_address.refresh_from_db()
        self.assertEqual(self.user.email, "byron@example.com")
        self.assertEqual(self.email_address.email, "byron@example.com")
        self.assertFalse(self.email_address.verified)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ["byron@example.com"])

    def test_correct_email_rejects_already_verified(
        self,
    ) -> None:
        self.email_address.verified = True
        self.email_address.save(update_fields=["verified"])
        response = self.client.post(
            "/api/v1/auth/register/correct-email",
            data={
                "src_api_key": "irrelevant",
                "new_email": "byron@example.com",
            },
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["error"], "already_verified")

    def test_correct_email_rejects_email_taken(
        self,
    ) -> None:
        User = get_user_model()
        other = User.objects.create_user(  # type: ignore
            username="other",
            email="taken@example.com",
            password="supersecret123",
        )
        EmailAddress.objects.create(
            user=other,
            email="taken@example.com",
            primary=True,
            verified=True,
        )
        response = self.client.post(
            "/api/v1/auth/register/correct-email",
            data={
                "src_api_key": "irrelevant",
                "new_email": "taken@example.com",
            },
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["error"], "email_taken")

    def test_correct_email_invalid_src_key(
        self,
    ) -> None:
        self._src_patch.stop()
        with patch("api.v1.routers.auth.register.http_requests.get") as mock_get:
            mock_get.return_value.status_code = 401
            response = self.client.post(
                "/api/v1/auth/register/correct-email",
                data={
                    "src_api_key": "bad",
                    "new_email": "byron@example.com",
                },
                content_type="application/json",
            )
        self.assertEqual(response.status_code, 400)
        self._src_patch = patch(
            "api.v1.routers.auth.register.http_requests.get",
        )
        self._src_patch.start()
