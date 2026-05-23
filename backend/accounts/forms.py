import logging

import requests as http_requests
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

    def __init__(self, *args, **kwargs) -> None:
        self._src_player_id: str | None = None
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
        email = self.cleaned_data["email"]
        if User.objects.filter(email__iexact=email).exists():
            raise ValidationError("email_taken", code="email_taken")
        return email

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

    def clean(
        self,
    ) -> dict:
        cleaned = super().clean()
        if self.sociallogin is not None:
            _check_oauth_unique(self.sociallogin)
        return cleaned

    @transaction.atomic
    def signup(
        self,
        request: HttpRequest,
        user: AbstractBaseUser,
    ) -> AbstractBaseUser:
        user.username = self.cleaned_data["username"]
        user.email = self.cleaned_data["email"]
        user.set_unusable_password()
        if self.cleaned_data.get("save_key"):
            user.encrypted_api_key = encrypt_src_key(self.cleaned_data["src_api_key"])
        user.save()
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
