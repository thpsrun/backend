import logging

import requests as http_requests
from allauth.account.models import EmailAddress
from allauth.headless.socialaccount.inputs import SignupInput
from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AbstractBaseUser
from django.core.exceptions import ValidationError
from django.db import transaction
from django.http import HttpRequest
from srl.encryption import encrypt_src_key
from srl.models import Players, RunPlayers

from accounts.adapters import _check_oauth_unique

logger = logging.getLogger(__name__)

User = get_user_model()

SRC_PROFILE_URL = "https://www.speedrun.com/api/v1/profile"


class SRCSignupInput(SignupInput):
    username = forms.CharField(max_length=150)
    email = forms.EmailField()
    src_api_key = forms.CharField(max_length=64)
    save_key = forms.BooleanField(required=False)

    def __init__(
        self,
        *args,
        **kwargs,
    ) -> None:
        self._src_player_id: str | None = None
        kwargs.setdefault("email_required", False)
        super().__init__(*args, **kwargs)

    def clean_username(
        self,
    ) -> str:
        username = self.cleaned_data["username"]
        if User.objects.filter(username__iexact=username).exists():
            raise ValidationError("username_taken", code="username_taken")
        return username

    def clean_email(
        self,
    ) -> str:
        # Email may be blank for OAuth signups; the provider address is resolved
        # in clean(), where the uniqueness check now lives.
        return self.cleaned_data.get("email", "")

    def clean_src_api_key(
        self,
    ) -> str:
        key = self.cleaned_data["src_api_key"]
        try:
            resp = http_requests.get(
                SRC_PROFILE_URL,
                headers={"X-API-Key": key},
                timeout=10,
            )
        except http_requests.RequestException as exc:
            logger.warning("SRC profile request failed: %s", exc)
            raise ValidationError("src_unreachable", code="src_unreachable")
        if resp.status_code != 200:
            raise ValidationError("src_invalid", code="src_invalid")
        try:
            data = resp.json()
            self._src_player_id = data["data"]["id"]
        except (KeyError, ValueError):
            raise ValidationError("src_invalid", code="src_invalid")
        return key

    def _provider_email(
        self,
    ) -> str | None:
        if self.sociallogin is None:
            return None
        addresses = self.sociallogin.email_addresses
        if not addresses:
            return None
        primary = next(
            (addr for addr in addresses if addr.primary),
            None,
        )
        chosen = primary or addresses[0]
        return chosen.email

    def _resolve_email(
        self,
        typed_email: str,
    ) -> str:
        final_email = self._provider_email() or typed_email or ""
        if not final_email:
            raise ValidationError("email_required", code="email_required")
        if User.objects.filter(email__iexact=final_email).exists():
            raise ValidationError("email_taken", code="email_taken")
        return final_email

    def clean(
        self,
    ) -> dict:
        cleaned = super().clean()
        if self.sociallogin is not None:
            _check_oauth_unique(self.sociallogin)
        try:
            cleaned["email"] = self._resolve_email(cleaned.get("email") or "")
        except ValidationError as exc:
            self.add_error("email", exc)
        return cleaned

    @transaction.atomic
    def signup(
        self,
        request: HttpRequest,
        user: AbstractBaseUser,
    ) -> AbstractBaseUser:
        form_email = self.cleaned_data["email"]
        user.username = self.cleaned_data["username"]
        user.email = form_email
        user.set_unusable_password()
        if self.cleaned_data.get("save_key"):
            user.encrypted_api_key = encrypt_src_key(self.cleaned_data["src_api_key"])
        user.save()

        if self.sociallogin is not None:
            matching = next(
                (
                    addr
                    for addr in self.sociallogin.email_addresses
                    if addr.email.lower() == form_email.lower()
                ),
                None,
            )
            for addr in self.sociallogin.email_addresses:
                if addr is matching:
                    continue
                addr.primary = False
                # Strip any provider-verified flag (Discord supplies verified=True) so a
                # non-matching address can't satisfy has_verified_email and skip our
                # confirmation under SOCIALACCOUNT_EMAIL_VERIFICATION="mandatory".
                addr.verified = False
            if matching is not None:
                matching.primary = True
                matching.verified = False
            else:
                self.sociallogin.email_addresses.insert(
                    0,
                    EmailAddress(
                        email=form_email,
                        primary=True,
                        verified=False,
                    ),
                )
        if self._src_player_id is not None:
            player = Players.objects.filter(id=self._src_player_id).first()
            if player is None:
                raise ValidationError("src_player_not_found")

            if player.claim_status != Players.ClaimStatus.UNCLAIMED:
                raise ValidationError("src_player_already_claimed")

            has_verified_run = RunPlayers.objects.filter(
                player=player,
                run__vid_status="verified",
            ).exists()

            if not has_verified_run:
                raise ValidationError("no_verified_run")

            player.user = user
            player.claim_status = Players.ClaimStatus.CLAIMED
            player.sync_paused = True
            player.save(
                update_fields=["user", "claim_status", "sync_paused"],
            )
        return user
