from __future__ import annotations

from typing import Any

from allauth.socialaccount.models import SocialApp, SocialToken
from django.contrib import admin
from django.contrib.admin import AdminSite
from django.contrib.sites.models import Site
from django.http import HttpRequest
from rest_framework_api_key.models import APIKey as _LegacyAbstractAPIKey

from api.models import APIActivityLog, APIKey

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
    """AdminSite subclass that folds the allauth apps into one nav section."""

    def get_app_list(
        self,
        request: HttpRequest,
        app_label: str | None = None,
    ) -> list[dict[str, Any]]:
        """Regroup allauth models under a single "User Accounts" app entry."""
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
    """Admin for API keys; the hash/prefix are read-only since keys are never re-shown."""

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


@admin.register(APIActivityLog)
class APIActivityLogAdmin(admin.ModelAdmin):
    """Read-only viewer: log rows are written by middleware and must stay tamper-proof."""

    list_display = (
        "created_at",
        "method",
        "path",
        "status_code",
        "auth_method",
        "user",
        "key_label_snapshot",
        "target_repr",
        "ip",
    )
    list_filter = (
        "auth_method",
        "method",
        "action",
        "status_code",
        "target_app",
        "target_model",
    )
    search_fields = (
        "path",
        "user__username",
        "key_label_snapshot",
        "target_id",
        "target_repr",
        "ip",
    )
    date_hierarchy = "created_at"
    ordering = ("-created_at",)
    list_select_related = ("user", "api_key")
    readonly_fields = tuple(field.name for field in APIActivityLog._meta.get_fields())

    def has_add_permission(
        self,
        request: HttpRequest,
    ) -> bool:
        return False

    def has_change_permission(
        self,
        request: HttpRequest,
        obj: Any = None,
    ) -> bool:
        return False

    def has_delete_permission(
        self,
        request: HttpRequest,
        obj: Any = None,
    ) -> bool:
        return False
