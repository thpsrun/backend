from __future__ import annotations

import json

from allauth.mfa.models import Authenticator
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.core.cache import cache
from django.http import HttpResponse
from django.test import RequestFactory, TestCase, override_settings

from accounts.middleware import MFASetupRequiredMiddleware
from accounts.privileges import is_gated, social_login_requires_mfa
from srl.models.games import Games
from srl.models.players import Players

User = get_user_model()


def _ok_view(request):
    return HttpResponse("ok")


@override_settings(
    CACHES={
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        },
    },
    MFA_ENFORCE_FOR_PRIVILEGED=True,
)
class MFAEnforcementTests(TestCase):
    def setUp(self) -> None:
        cache.clear()
        self.factory = RequestFactory()
        self.middleware = MFASetupRequiredMiddleware(_ok_view)

    def _make_user(self, username, is_superuser=False):
        user = User.objects.create_user(  # type: ignore
            username=username,
            email=f"{username}@example.com",
            password="supersecret123",
        )
        if is_superuser:
            user.is_superuser = True
            user.is_staff = True
            user.save(update_fields=["is_superuser", "is_staff"])
        return user

    def _add_factor(self, user, factor_type):
        return Authenticator.objects.create(
            user=user,
            type=factor_type,
            data={},
        )

    def _request(self, user, path="/api/v1/games"):
        request = self.factory.get(path)
        request.user = user
        return self.middleware(request)

    def test_superuser_without_factor_is_gated(self) -> None:
        user = self._make_user("super1", is_superuser=True)
        response = self._request(user)
        self.assertEqual(response.status_code, 403)
        body = json.loads(response.content)
        self.assertEqual(body["data"]["flows"][0]["id"], "mfa_setup_required")
        self.assertEqual(body["data"]["accepted_types"], ["totp", "webauthn"])

    def test_superuser_with_totp_not_gated(self) -> None:
        user = self._make_user("super2", is_superuser=True)
        self._add_factor(user, Authenticator.Type.TOTP)
        self.assertEqual(self._request(user).status_code, 200)

    def test_superuser_with_passkey_not_gated(self) -> None:
        user = self._make_user("super3", is_superuser=True)
        self._add_factor(user, Authenticator.Type.WEBAUTHN)
        self.assertEqual(self._request(user).status_code, 200)

    def test_recovery_codes_only_still_gated(self) -> None:
        user = self._make_user("super4", is_superuser=True)
        self._add_factor(user, Authenticator.Type.RECOVERY_CODES)
        self.assertEqual(self._request(user).status_code, 403)

    def test_non_privileged_user_not_gated(self) -> None:
        user = self._make_user("plain1")
        self.assertEqual(self._request(user).status_code, 200)

    def test_anonymous_not_gated(self) -> None:
        self.assertEqual(self._request(AnonymousUser()).status_code, 200)

    def test_moderator_without_factor_is_gated(self) -> None:
        user = self._make_user("mod1")
        player = Players.objects.create(
            id="modp1",
            name="mod1",
            url="https://example.com/mod1",
            claim_status=Players.ClaimStatus.CLAIMED,
            user=user,
        )
        game = Games.objects.create(
            id="modg1",
            name="Mod Game",
            slug="mod-game",
            release="2000-01-01",
            boxart="https://example.com/cover.png",
        )
        game.moderators.add(player)
        self.assertEqual(self._request(user).status_code, 403)

    def test_allowlisted_allauth_path_passes_while_gated(self) -> None:
        user = self._make_user("super5", is_superuser=True)
        response = self._request(user, path="/_allauth/browser/v1/auth/session")
        self.assertEqual(response.status_code, 200)

    def test_allowlisted_accounts_path_passes_while_gated(self) -> None:
        user = self._make_user("super9", is_superuser=True)
        response = self._request(user, path="/accounts/oauth-login-complete/")
        self.assertEqual(response.status_code, 200)

    def test_admin_illiad_not_gated(self) -> None:
        user = self._make_user("super6", is_superuser=True)
        self.assertEqual(self._request(user, path="/illiad/").status_code, 200)

    def test_gate_lifts_after_totp_created(self) -> None:
        user = self._make_user("super7", is_superuser=True)
        self.assertTrue(is_gated(user))
        self._add_factor(user, Authenticator.Type.TOTP)
        self.assertFalse(is_gated(user))

    @override_settings(MFA_ENFORCE_FOR_PRIVILEGED=False)
    def test_kill_switch_disables_enforcement(self) -> None:
        user = self._make_user("super8", is_superuser=True)
        self.assertEqual(self._request(user).status_code, 200)

    def test_social_challenge_totp_only(self) -> None:
        user = self._make_user("soc1")
        self._add_factor(user, Authenticator.Type.TOTP)
        self.assertTrue(social_login_requires_mfa(user))

    def test_social_challenge_totp_and_recovery_codes(self) -> None:
        user = self._make_user("soc2")
        self._add_factor(user, Authenticator.Type.TOTP)
        self._add_factor(user, Authenticator.Type.RECOVERY_CODES)
        self.assertTrue(social_login_requires_mfa(user))

    def test_social_challenge_passkey_only_exempt(self) -> None:
        user = self._make_user("soc3")
        self._add_factor(user, Authenticator.Type.WEBAUTHN)
        self.assertFalse(social_login_requires_mfa(user))

    def test_social_challenge_totp_and_passkey_exempt(self) -> None:
        user = self._make_user("soc4")
        self._add_factor(user, Authenticator.Type.TOTP)
        self._add_factor(user, Authenticator.Type.WEBAUTHN)
        self.assertFalse(social_login_requires_mfa(user))

    def test_social_challenge_no_factor(self) -> None:
        user = self._make_user("soc5")
        self.assertFalse(social_login_requires_mfa(user))
