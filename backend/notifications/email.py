from collections.abc import Callable
from typing import Any

from django.conf import settings

from notifications import kinds

SUBJECTS: dict[str, str] = {
    kinds.RUN_APPROVED: "Run approved",
    kinds.RUN_DENIED: "Run denied",
    kinds.RUN_REVIEW: "Your run was sent back for review",
    kinds.MOD_PROMOTED: "You were promoted to moderator",
    kinds.API_KEY_EXPIRING: "An API key is expiring soon",
    kinds.USER_DATA_EXPORT_READY: "Your data export is ready",
    kinds.USER_DATA_EXPORT_FAILED: "Your data export failed",
}


UrlBuilder = Callable[[str, dict[str, Any]], str]


def _run_approved_cta(target_id: str, payload: dict[str, Any]) -> str:
    slug = payload.get("game_id")
    if not slug:
        return f"{settings.FRONTEND_URL}/submissions"
    return f"{settings.FRONTEND_URL}/{slug}"


def _submissions_cta(target_id: str, payload: dict[str, Any]) -> str:
    return f"{settings.FRONTEND_URL}/submissions"


def _game_manage_cta(target_id: str, payload: dict[str, Any]) -> str:
    slug = target_id or payload.get("game_id")
    if not slug:
        return settings.FRONTEND_URL
    return f"{settings.FRONTEND_URL}/{slug}/manage"


def _api_keys_cta(target_id: str, payload: dict[str, Any]) -> str:
    return f"{settings.FRONTEND_URL}/profile/settings/api-keys"


def _data_export_cta(target_id: str, payload: dict[str, Any]) -> str:
    return f"{settings.FRONTEND_URL}/profile/settings/danger"


def _game_target_cta(target_id: str, payload: dict[str, Any]) -> str:
    if not target_id:
        return settings.FRONTEND_URL
    return f"{settings.FRONTEND_URL}/{target_id}"


KIND_URL_BUILDERS: dict[str, UrlBuilder] = {
    kinds.RUN_APPROVED: _run_approved_cta,
    kinds.RUN_DENIED: _submissions_cta,
    kinds.RUN_REVIEW: _submissions_cta,
    kinds.MOD_PROMOTED: _game_manage_cta,
    kinds.API_KEY_EXPIRING: _api_keys_cta,
    kinds.USER_DATA_EXPORT_READY: _data_export_cta,
    kinds.USER_DATA_EXPORT_FAILED: _data_export_cta,
    kinds.USER_DATA_EXPORT_GROUP: _data_export_cta,
}


TARGET_URL_BUILDERS: dict[str, UrlBuilder] = {
    "game": _game_target_cta,
}


def build_subject(
    kind: str,
    fallback_title: str,
) -> str:
    base = SUBJECTS.get(kind, fallback_title)
    prefix = getattr(settings, "ACCOUNT_EMAIL_SUBJECT_PREFIX", "")
    return f"{prefix}{base}"


def build_cta_url(
    *,
    kind: str,
    target_type: str,
    target_id: str,
    payload: dict[str, Any],
) -> str:
    kind_builder = KIND_URL_BUILDERS.get(kind)
    if kind_builder is not None:
        return kind_builder(target_id, payload)

    target_builder = TARGET_URL_BUILDERS.get(target_type)
    if target_builder is None or not target_id:
        return settings.FRONTEND_URL
    return target_builder(target_id, payload)


def preferences_url() -> str:
    return f"{settings.FRONTEND_URL}/profile/settings/notifications"
