import re

from allauth.account.internal.flows.login import AUTHENTICATION_METHODS_SESSION_KEY
from allauth.core import context
from allauth.core.exceptions import ImmediateHttpResponse
from allauth.mfa.adapter import DefaultMFAAdapter
from allauth.mfa.models import Authenticator
from allauth.socialaccount.adapter import DefaultSocialAccountAdapter
from allauth.socialaccount.models import SocialAccount, SocialLogin
from django.conf import settings
from django.contrib.auth.base_user import AbstractBaseUser
from django.core.exceptions import ValidationError
from django.db import transaction
from django.http import HttpRequest, HttpResponseRedirect
from srl.models import Players

from accounts.oauth_connect import (
    _CONNECT_COMPLETE_URL_PATH,
    handle_connect,
)
from accounts.oauth_connect import (
    clear_intent as clear_connect_intent,
)
from accounts.oauth_connect import (
    peek_intent as peek_connect_intent,
)
from accounts.oauth_login import handle_login
from accounts.oauth_login import peek_intent as peek_login_intent
from accounts.oauth_reauth import handle_reauth
from accounts.oauth_reauth import peek_intent as peek_reauth_intent
from accounts.oauth_signup import handle_signup
from accounts.oauth_signup import peek_intent as peek_signup_intent
from accounts.privileges import social_login_requires_mfa

TWITCH_LOGIN_RE: re.Pattern[str] = re.compile(r"^[A-Za-z0-9_]{1,25}$")


def _check_oauth_unique(
    sociallogin: SocialLogin,
    exclude_user: AbstractBaseUser | None = None,
) -> None:
    extra = sociallogin.account.extra_data or {}
    provider = sociallogin.account.provider
    qs = Players.objects.exclude(user__isnull=True)

    if exclude_user is not None:
        qs = qs.exclude(user=exclude_user)

    if provider == "discord":
        handle = (extra.get("username") or "")[:32]
        if handle and qs.filter(discord__iexact=handle).exists():
            raise ValidationError("discord_handle_taken", code="discord_handle_taken")

    elif provider == "twitch":
        login = extra.get("login")
        if login and TWITCH_LOGIN_RE.match(login):
            url = f"https://twitch.tv/{login}"
            if qs.filter(twitch__iexact=url).exists():
                raise ValidationError("twitch_handle_taken", code="twitch_handle_taken")


class SocialAccountAdapter(DefaultSocialAccountAdapter):
    def is_open_for_signup(  # type: ignore
        self,
        request: HttpRequest,
        sociallogin: SocialLogin,
    ) -> bool:
        return True

    def pre_social_login(
        self,
        request: HttpRequest,
        sociallogin: SocialLogin,
    ) -> None:
        process = sociallogin.state.get("process")

        if process == "connect" and getattr(request.user, "is_authenticated", False):
            exclude_user = request.user
        else:
            exclude_user = sociallogin.user if sociallogin.is_existing else None
        _check_oauth_unique(sociallogin, exclude_user=exclude_user)  # type: ignore

        if process == "connect":
            connect_intent = peek_connect_intent(request)
            if connect_intent is None:
                clear_connect_intent(request)
                raise ImmediateHttpResponse(
                    HttpResponseRedirect(
                        f"{_CONNECT_COMPLETE_URL_PATH}"
                        f"?status=error&reason=intent_expired",
                    ),
                )
            handle_connect(request, sociallogin, connect_intent)
            return

        reauth_intent = peek_reauth_intent(request)
        if reauth_intent is not None:
            handle_reauth(request, sociallogin, reauth_intent)
            return

        signup_intent = peek_signup_intent(request)
        if signup_intent is not None:
            handle_signup(request, sociallogin, signup_intent)
            return

        login_intent = peek_login_intent(request)
        if login_intent is not None:
            handle_login(request, sociallogin, login_intent)
            return

        if sociallogin.user:
            if not sociallogin.is_existing:
                raise ImmediateHttpResponse(
                    HttpResponseRedirect(f"{settings.FRONTEND_URL}/login/no-link/"),
                )

            if not sociallogin.user.is_active:
                raise ImmediateHttpResponse(
                    HttpResponseRedirect(f"{settings.FRONTEND_URL}/login/banned/"),
                )

    def get_connect_redirect_url(
        self,
        request: HttpRequest,
        socialaccount: SocialAccount,
    ) -> str:
        clear_connect_intent(request)
        return (
            f"{_CONNECT_COMPLETE_URL_PATH}"
            f"?status=ok&provider={socialaccount.provider}"
        )

    def validate_disconnect(
        self,
        account: SocialAccount,
        accounts: list[SocialAccount],
    ) -> None:
        # This is additional logic to lock the user from removing their password AND their
        # social media - otherwise a user would be completely locked out.
        with transaction.atomic():
            user = (
                type(account.user).objects.select_for_update().get(pk=account.user.pk)
            )
            if user.has_usable_password():
                return super().validate_disconnect(account, accounts)

            remaining_social = [a for a in accounts if a.pk != account.pk]
            has_passkey = Authenticator.objects.filter(
                user=user,
                type="webauthn",
            ).exists()

            if not remaining_social and not has_passkey:
                raise ValidationError("last_auth_method")

            return super().validate_disconnect(account, accounts)


class MFAAdapter(DefaultMFAAdapter):
    def is_mfa_enabled(
        self,
        user,
        types=None,
    ) -> bool:
        if user.is_anonymous:
            return False

        request = context.request

        if request is not None:
            methods = request.session.get(AUTHENTICATION_METHODS_SESSION_KEY, [])
            if methods and methods[-1].get("method") == "socialaccount":
                if not social_login_requires_mfa(user):
                    return False
                return super().is_mfa_enabled(user, types=types)

        return super().is_mfa_enabled(user, types=types)

    def can_delete_authenticator(
        self,
        authenticator: Authenticator,
    ) -> bool:
        if authenticator.type != "webauthn":
            return super().can_delete_authenticator(authenticator)

        user = authenticator.user
        if user.has_usable_password():
            return super().can_delete_authenticator(authenticator)

        other_passkey = (
            Authenticator.objects.filter(
                user=user,
                type="webauthn",
            )
            .exclude(pk=authenticator.pk)
            .exists()
        )
        has_social = SocialAccount.objects.filter(user=user).exists()
        if not other_passkey and not has_social:
            return False
        return super().can_delete_authenticator(authenticator)
