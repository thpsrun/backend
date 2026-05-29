from __future__ import annotations

from unittest.mock import patch

from accounts.forms import SRCSignupInput
from allauth.account.models import EmailAddress
from allauth.headless.socialaccount.inputs import SignupInput
from allauth.socialaccount.models import SocialAccount, SocialLogin
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import RequestFactory, TestCase

User = get_user_model()


def _build_signup_form(
    email: str,
    username: str,
    provider_addresses: list[EmailAddress],
    provider: str = "discord",
) -> SRCSignupInput:
    form = SRCSignupInput.__new__(SRCSignupInput)
    form._src_player_id = None
    form.cleaned_data = {
        "email": email,
        "username": username,
        "src_api_key": "irrelevant",
        "save_key": False,
    }
    sociallogin = SocialLogin()
    sociallogin.account = SocialAccount(provider=provider, uid="provider-uid")
    sociallogin.email_addresses = provider_addresses
    form.sociallogin = sociallogin
    return form


def _form_with_provider(
    provider_addresses: list[EmailAddress],
    provider: str = "discord",
) -> SRCSignupInput:
    form = SRCSignupInput.__new__(SRCSignupInput)
    form._src_player_id = None
    sociallogin = SocialLogin()
    sociallogin.account = SocialAccount(provider=provider, uid="provider-uid")
    sociallogin.email_addresses = provider_addresses
    form.sociallogin = sociallogin
    return form


class OAuthSignupEmailResolutionTest(TestCase):

    def test_provider_email_wins_over_typed(
        self,
    ) -> None:
        form = _form_with_provider(
            provider_addresses=[
                EmailAddress(
                    email="discord@example.com",
                    verified=True,
                    primary=True,
                ),
            ],
        )
        self.assertEqual(
            form._resolve_email("typed@example.com"),
            "discord@example.com",
        )

    def test_provider_email_used_when_email_omitted(
        self,
    ) -> None:
        form = _form_with_provider(
            provider_addresses=[
                EmailAddress(
                    email="discord@example.com",
                    verified=True,
                    primary=True,
                ),
            ],
        )
        self.assertEqual(form._resolve_email(""), "discord@example.com")

    def test_primary_provider_address_preferred(
        self,
    ) -> None:
        form = _form_with_provider(
            provider_addresses=[
                EmailAddress(
                    email="secondary@example.com",
                    verified=True,
                    primary=False,
                ),
                EmailAddress(
                    email="primary@example.com",
                    verified=True,
                    primary=True,
                ),
            ],
        )
        self.assertEqual(form._resolve_email(""), "primary@example.com")

    def test_typed_email_used_when_provider_has_none(
        self,
    ) -> None:
        form = _form_with_provider(
            provider_addresses=[],
            provider="twitch",
        )
        self.assertEqual(
            form._resolve_email("me@example.com"),
            "me@example.com",
        )

    def test_missing_email_raises_email_required(
        self,
    ) -> None:
        form = _form_with_provider(
            provider_addresses=[],
            provider="twitch",
        )
        with self.assertRaises(ValidationError) as ctx:
            form._resolve_email("")
        self.assertEqual(ctx.exception.code, "email_required")

    def test_existing_email_raises_email_taken(
        self,
    ) -> None:
        User.objects.create(
            username="existing",
            email="discord@example.com",
        )
        form = _form_with_provider(
            provider_addresses=[
                EmailAddress(
                    email="discord@example.com",
                    verified=True,
                    primary=True,
                ),
            ],
        )
        with self.assertRaises(ValidationError) as ctx:
            form._resolve_email("")
        self.assertEqual(ctx.exception.code, "email_taken")

    def test_init_passes_email_required_false(
        self,
    ) -> None:
        captured: dict = {}

        def _capture(
            inner_self,
            *args,
            **kwargs,
        ) -> None:
            captured.update(kwargs)

        with patch.object(
            SignupInput,
            "__init__",
            _capture,
        ):
            SRCSignupInput(sociallogin=None)

        self.assertIs(captured.get("email_required"), False)


class OAuthSignupEmailVerificationTest(TestCase):

    def setUp(
        self,
    ) -> None:
        self.request = RequestFactory().post(
            "/_allauth/browser/v1/auth/provider/signup",
        )

    def test_extra_provider_addresses_forced_unverified(
        self,
    ) -> None:
        # clean() resolves to the provider primary; signup() must still force every
        # other provider address unverified, or has_verified_email() would skip
        # the confirmation stage.
        form = _build_signup_form(
            email="primary@example.com",
            username="multirunner",
            provider_addresses=[
                EmailAddress(
                    email="primary@example.com",
                    verified=True,
                    primary=True,
                ),
                EmailAddress(
                    email="secondary@example.com",
                    verified=True,
                    primary=False,
                ),
            ],
        )
        user = form.signup(self.request, User())

        self.assertEqual(user.email, "primary@example.com")
        sl = form.sociallogin
        self.assertTrue(all(not addr.verified for addr in sl.email_addresses))
        primary = [addr for addr in sl.email_addresses if addr.primary]
        self.assertEqual(len(primary), 1)
        self.assertEqual(primary[0].email, "primary@example.com")

    def test_matching_provider_email_is_forced_unverified(
        self,
    ) -> None:
        # User types the same email Discord already verified; we still require confirmation.
        form = _build_signup_form(
            email="same@example.com",
            username="matchrunner",
            provider_addresses=[
                EmailAddress(
                    email="same@example.com",
                    verified=True,
                    primary=True,
                ),
            ],
        )
        user = form.signup(self.request, User())

        self.assertEqual(user.email, "same@example.com")
        sl = form.sociallogin
        self.assertTrue(all(not addr.verified for addr in sl.email_addresses))
        match = [
            addr for addr in sl.email_addresses if addr.email == "same@example.com"
        ]
        self.assertEqual(len(match), 1)
        self.assertTrue(match[0].primary)
        self.assertFalse(match[0].verified)

    def test_no_provider_email_inserts_unverified_primary(
        self,
    ) -> None:
        # Twitch path: no provider-supplied address, so the typed email is inserted.
        form = _build_signup_form(
            email="twitchuser@example.com",
            username="twitchrunner",
            provider="twitch",
            provider_addresses=[],
        )
        user = form.signup(self.request, User())

        self.assertEqual(user.email, "twitchuser@example.com")
        sl = form.sociallogin
        self.assertEqual(len(sl.email_addresses), 1)
        self.assertEqual(sl.email_addresses[0].email, "twitchuser@example.com")
        self.assertTrue(sl.email_addresses[0].primary)
        self.assertFalse(sl.email_addresses[0].verified)
