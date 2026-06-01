from __future__ import annotations

from unittest.mock import patch

from allauth.account.models import EmailAddress, EmailConfirmationHMAC
from django.contrib.auth import get_user_model
from django.core import mail
from django.core.cache import cache
from django.test import Client, TestCase, override_settings
from srl.models.players import Players


class MeEmailGetTest(TestCase):

    def setUp(
        self,
    ) -> None:
        User = get_user_model()
        self.user = User.objects.create_user(  # type: ignore
            username="cleo",
            email="cleo@example.com",
            password="supersecret123",
        )
        EmailAddress.objects.create(
            user=self.user,
            email=self.user.email,
            primary=True,
            verified=True,
        )
        Players.objects.create(
            id="cleo-src-id",
            name="cleo",
            url="",
            user=self.user,
            claim_status=Players.ClaimStatus.CLAIMED,
        )
        self.client = Client()
        self.client.force_login(self.user)

    def test_get_email_returns_current_state(
        self,
    ) -> None:
        response = self.client.get("/api/v1/auth/me/email")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["email"], "cleo@example.com")
        self.assertTrue(body["verified"])
        self.assertIsNone(body["pending_email"])
        self.assertIsNone(body["pending_expires_at"])

    def test_get_email_returns_pending(
        self,
    ) -> None:
        EmailAddress.objects.create(
            user=self.user,
            email="cleo-new@example.com",
            primary=False,
            verified=False,
        )
        response = self.client.get("/api/v1/auth/me/email")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["pending_email"], "cleo-new@example.com")
        self.assertIsNone(body["pending_expires_at"])

    def test_get_email_requires_auth(
        self,
    ) -> None:
        self.client.logout()
        response = self.client.get("/api/v1/auth/me/email")
        self.assertEqual(response.status_code, 401)


class MeEmailChangeTest(TestCase):

    def setUp(
        self,
    ) -> None:
        User = get_user_model()
        self.user = User.objects.create_user(  # type: ignore
            username="dora",
            email="dora@example.com",
            password="supersecret123",
        )
        EmailAddress.objects.create(
            user=self.user,
            email=self.user.email,
            primary=True,
            verified=True,
        )
        Players.objects.create(
            id="dora-src-id",
            name="dora",
            url="",
            user=self.user,
            claim_status=Players.ClaimStatus.CLAIMED,
        )
        self.client = Client()
        self.client.force_login(self.user)
        self._reauth_patch = patch(
            "api.v1.routers.auth.me_email.did_recently_authenticate",
            return_value=True,
        )
        self._reauth_patch.start()
        self.addCleanup(self._reauth_patch.stop)

    @override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
    def test_change_creates_pending_and_sends_code(
        self,
    ) -> None:
        mail.outbox = []
        response = self.client.post(
            "/api/v1/auth/me/email/change",
            data={"new_email": "dora-new@example.com"},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 202)
        body = response.json()
        self.assertEqual(body["status"], "verification_sent")
        self.assertEqual(body["new_email"], "dora-new@example.com")
        pending = EmailAddress.objects.get(
            user=self.user,
            primary=False,
            verified=False,
        )
        self.assertEqual(pending.email, "dora-new@example.com")
        recipients = {addr for m in mail.outbox for addr in m.to}
        self.assertIn("dora-new@example.com", recipients)
        self.assertIn("dora@example.com", recipients)

    def test_change_rejects_same_email(
        self,
    ) -> None:
        response = self.client.post(
            "/api/v1/auth/me/email/change",
            data={"new_email": "dora@example.com"},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"], "same_email")

    def test_change_rejects_email_taken(
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
            "/api/v1/auth/me/email/change",
            data={"new_email": "taken@example.com"},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["error"], "email_taken")

    def test_change_replaces_prior_pending(
        self,
    ) -> None:
        EmailAddress.objects.create(
            user=self.user,
            email="dora-old-pending@example.com",
            primary=False,
            verified=False,
        )
        response = self.client.post(
            "/api/v1/auth/me/email/change",
            data={"new_email": "dora-newest@example.com"},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 202)
        pending_rows = EmailAddress.objects.filter(
            user=self.user,
            primary=False,
            verified=False,
        )
        self.assertEqual(pending_rows.count(), 1)
        self.assertEqual(pending_rows.first().email, "dora-newest@example.com")

    def test_change_requires_reauth(
        self,
    ) -> None:
        with patch(
            "api.v1.routers.auth.me_email.did_recently_authenticate",
            return_value=False,
        ):
            response = self.client.post(
                "/api/v1/auth/me/email/change",
                data={"new_email": "dora-new@example.com"},
                content_type="application/json",
            )
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()["error"], "reauth_required")


class MeEmailVerifyTest(TestCase):

    def setUp(
        self,
    ) -> None:
        User = get_user_model()
        self.user = User.objects.create_user(  # type: ignore
            username="elsa",
            email="elsa@example.com",
            password="supersecret123",
        )
        self.old_primary = EmailAddress.objects.create(
            user=self.user,
            email=self.user.email,
            primary=True,
            verified=True,
        )
        self.pending = EmailAddress.objects.create(
            user=self.user,
            email="elsa-new@example.com",
            primary=False,
            verified=False,
        )
        self.valid_key = EmailConfirmationHMAC(self.pending).key
        Players.objects.create(
            id="elsa-src-id",
            name="elsa",
            url="",
            user=self.user,
            claim_status=Players.ClaimStatus.CLAIMED,
        )
        self.client = Client()
        self.client.force_login(self.user)

    def test_verify_promotes_new_email(
        self,
    ) -> None:
        response = self.client.post(
            "/api/v1/auth/me/email/verify",
            data={"code": self.valid_key},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["player"]["email"], "elsa-new@example.com")
        self.assertTrue(body["player"]["email_verified"])
        self.assertIsNone(body["player"]["pending_email"])

        self.user.refresh_from_db()
        self.assertEqual(self.user.email, "elsa-new@example.com")
        self.assertFalse(
            EmailAddress.objects.filter(pk=self.old_primary.pk).exists(),
        )
        promoted = EmailAddress.objects.get(pk=self.pending.pk)
        self.assertTrue(promoted.primary)
        self.assertTrue(promoted.verified)

    def test_verify_with_bad_code(
        self,
    ) -> None:
        response = self.client.post(
            "/api/v1/auth/me/email/verify",
            data={"code": "999999"},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"], "invalid_or_expired_code")

    def test_verify_with_no_pending(
        self,
    ) -> None:
        self.pending.delete()
        response = self.client.post(
            "/api/v1/auth/me/email/verify",
            data={"code": self.valid_key},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"], "no_pending_change")


class MeEmailResendTest(TestCase):

    def setUp(
        self,
    ) -> None:
        User = get_user_model()
        self.user = User.objects.create_user(  # type: ignore
            username="fred",
            email="fred@example.com",
            password="supersecret123",
        )
        EmailAddress.objects.create(
            user=self.user,
            email=self.user.email,
            primary=True,
            verified=True,
        )
        Players.objects.create(
            id="fred-src-id",
            name="fred",
            url="",
            user=self.user,
            claim_status=Players.ClaimStatus.CLAIMED,
        )
        self.client = Client()
        self.client.force_login(self.user)

    @override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
    def test_resend_sends_code(
        self,
    ) -> None:
        EmailAddress.objects.create(
            user=self.user,
            email="fred-new@example.com",
            primary=False,
            verified=False,
        )
        mail.outbox = []
        response = self.client.post("/api/v1/auth/me/email/resend")
        self.assertEqual(response.status_code, 204)
        recipients = {addr for m in mail.outbox for addr in m.to}
        self.assertIn("fred-new@example.com", recipients)

    def test_resend_without_pending(
        self,
    ) -> None:
        response = self.client.post("/api/v1/auth/me/email/resend")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"], "no_pending_change")


class MeEmailCancelTest(TestCase):

    def setUp(
        self,
    ) -> None:
        User = get_user_model()
        self.user = User.objects.create_user(  # type: ignore
            username="gigi",
            email="gigi@example.com",
            password="supersecret123",
        )
        self.primary = EmailAddress.objects.create(
            user=self.user,
            email=self.user.email,
            primary=True,
            verified=True,
        )
        Players.objects.create(
            id="gigi-src-id",
            name="gigi",
            url="",
            user=self.user,
            claim_status=Players.ClaimStatus.CLAIMED,
        )
        self.client = Client()
        self.client.force_login(self.user)

    def test_cancel_removes_pending(
        self,
    ) -> None:
        EmailAddress.objects.create(
            user=self.user,
            email="gigi-new@example.com",
            primary=False,
            verified=False,
        )
        response = self.client.delete("/api/v1/auth/me/email/pending")
        self.assertEqual(response.status_code, 204)
        self.assertFalse(
            EmailAddress.objects.filter(
                user=self.user,
                primary=False,
                verified=False,
            ).exists(),
        )
        self.assertTrue(
            EmailAddress.objects.filter(pk=self.primary.pk).exists(),
        )

    def test_cancel_idempotent_when_no_pending(
        self,
    ) -> None:
        response = self.client.delete("/api/v1/auth/me/email/pending")
        self.assertEqual(response.status_code, 204)


class MeEmailRateLimitTest(TestCase):

    def setUp(
        self,
    ) -> None:
        cache.clear()
        User = get_user_model()
        self.user = User.objects.create_user(  # type: ignore
            username="harry",
            email="harry@example.com",
            password="supersecret123",
        )
        EmailAddress.objects.create(
            user=self.user,
            email=self.user.email,
            primary=True,
            verified=True,
        )
        Players.objects.create(
            id="harry-src-id",
            name="harry",
            url="",
            user=self.user,
            claim_status=Players.ClaimStatus.CLAIMED,
        )
        self.client = Client()
        self.client.force_login(self.user)
        self._reauth_patch = patch(
            "api.v1.routers.auth.me_email.did_recently_authenticate",
            return_value=True,
        )
        self._reauth_patch.start()
        self.addCleanup(self._reauth_patch.stop)

    @override_settings(DEBUG=False)
    def test_change_endpoint_rate_limited_at_4(
        self,
    ) -> None:
        for i in range(3):
            response = self.client.post(
                "/api/v1/auth/me/email/change",
                data={"new_email": f"harry-{i}@example.com"},
                content_type="application/json",
            )
            self.assertEqual(response.status_code, 202, f"call {i} failed")
        response = self.client.post(
            "/api/v1/auth/me/email/change",
            data={"new_email": "harry-4@example.com"},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 429)
