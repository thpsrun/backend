from allauth.account.internal.flows.login import AUTHENTICATION_METHODS_SESSION_KEY
from allauth.core import context
from allauth.core.exceptions import ImmediateHttpResponse
from allauth.mfa.adapter import DefaultMFAAdapter
from allauth.socialaccount.adapter import DefaultSocialAccountAdapter
from django.conf import settings
from django.http import HttpResponseRedirect


class SocialAccountAdapter(DefaultSocialAccountAdapter):
    def is_open_for_signup(  # type: ignore
        self,
        request,
        sociallogin,
    ) -> bool:
        # This disables the ability for social accounts to create new users.
        return False

    def pre_social_login(self, request, sociallogin):
        # On a connect flow (user is already logged in and linking from settings),
        # let allauth proceed so it can attach the SocialAccount to the current user.
        # The "must already be linked" rule only applies to the LOGIN flow.
        if sociallogin.state.get("process") == "connect":
            return
        if not sociallogin.is_existing:
            raise ImmediateHttpResponse(
                HttpResponseRedirect(f"{settings.FRONTEND_URL}/login/no-link/"),
            )


class MFAAdapter(DefaultMFAAdapter):
    def is_mfa_enabled(self, user, types=None) -> bool:
        if user.is_anonymous:
            return False
        request = context.request
        if request is not None:
            methods = request.session.get(AUTHENTICATION_METHODS_SESSION_KEY, [])
            if methods and methods[-1].get("method") == "socialaccount":
                return False
        return super().is_mfa_enabled(user, types=types)
