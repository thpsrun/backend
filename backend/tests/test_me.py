from __future__ import annotations

from allauth.account.models import EmailAddress
from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from srl.models.players import Players


class MeEmailFieldsTest(TestCase):

    def setUp(
        self,
    ) -> None:
        User = get_user_model()
        self.user = User.objects.create_user(  # type: ignore
            username="ada",
            email="ada@example.com",
            password="supersecret123",
        )
        EmailAddress.objects.create(
            user=self.user,
            email=self.user.email,
            verified=True,
            primary=True,
        )
        self.player = Players.objects.create(
            id="ada-src-id",
            name="ada",
            url="",
            user=self.user,
            claim_status=Players.ClaimStatus.CLAIMED,
        )
        self.client = Client()

    def test_me_returns_email_and_verified(
        self,
    ) -> None:
        self.client.force_login(self.user)
        response = self.client.get("/api/v1/auth/me")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["player"]["email"], "ada@example.com")
        self.assertTrue(body["player"]["email_verified"])
        self.assertIsNone(body["player"]["pending_email"])

    def test_me_returns_pending_email(
        self,
    ) -> None:
        EmailAddress.objects.create(
            user=self.user,
            email="ada-new@example.com",
            verified=False,
            primary=False,
        )
        self.client.force_login(self.user)
        response = self.client.get("/api/v1/auth/me")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["player"]["email"], "ada@example.com")
        self.assertTrue(body["player"]["email_verified"])
        self.assertEqual(body["player"]["pending_email"], "ada-new@example.com")
