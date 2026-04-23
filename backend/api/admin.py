from __future__ import annotations

from typing import Any

from allauth.socialaccount.models import SocialApp, SocialToken
from django.contrib import admin
from django.contrib.admin import AdminSite
from django.contrib.sites.models import Site
from django.http import HttpRequest
from rest_framework_api_key.models import APIKey as _LegacyAbstractAPIKey

from api.models import APIKey

# Django allauth registers some admin models that are unnecessary.
for adminmodel in (_LegacyAbstractAPIKey, Site, SocialApp, SocialToken):
    try:
        admin.site.unregister(adminmodel)
    except admin.sites.NotRegistered:
        pass


# Merge the scattered allauth app groups into a single "User Accounts" section
# with clearer model names.
_USER_ACCOUNT_APPS = {"account", "mfa", "socialaccount"}
_MODEL_RENAME: dict[str, str] = {
    "Email Addresses": "Verified Emails",
    "Authenticators": "MFA Devices",
    "Social Accounts": "Linked Accounts",
}


class _MergedAllauthAdminSite(AdminSite):
    def get_app_list(
        self,
        request: HttpRequest,
        app_label: str | None = None,
    ) -> list[dict[str, Any]]:
        app_list = super().get_app_list(request, app_label)  # type: ignore

        user_account_models: list[dict[str, Any]] = []
        filtered: list[dict[str, Any]] = []

        for app in app_list:
            if app["app_label"] in _USER_ACCOUNT_APPS:
                for model in app["models"]:
                    model["name"] = _MODEL_RENAME.get(model["name"], model["name"])
                user_account_models.extend(app["models"])
            else:
                filtered.append(app)

        if user_account_models:
            filtered.append(
                {
                    "name": "User Accounts",
                    "app_label": "account",
                    "app_url": "/illiad/account/",
                    "has_module_perms": True,
                    "models": sorted(user_account_models, key=lambda m: m["name"]),
                }
            )

        return filtered


admin.site.__class__ = _MergedAllauthAdminSite


@admin.register(APIKey)
class APIKeyAdmin(admin.ModelAdmin):
    list_display = (
        "label",
        "user",
        "prefix",
        "revoked",
        "revoked_reason",
        "last_used",
        "expiry_date",
    )
    list_filter = ("revoked", "revoked_reason")
    search_fields = ("label", "user__username", "prefix")
    readonly_fields = (
        "prefix",
        "hashed_key",
        "created",
        "last_used",
        "last_used_ip",
    )
