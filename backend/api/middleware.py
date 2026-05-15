from __future__ import annotations

import json
import logging
import re
from collections.abc import Callable
from typing import Any

from django.http import HttpRequest, HttpResponse
from django.utils import timezone

from api.client_ip import client_ip
from api.models import (
    APIActivityAction,
    APIActivityAuthMethod,
    APIActivityLog,
    APIKey,
)

logger = logging.getLogger(__name__)

MAX_LOG_BODY_SIZE = 10000
MAX_BODY_DISPLAY_LENGTH = 2000
MAX_USER_AGENT_LENGTH = 255
MAX_PATH_LENGTH = 512
MAX_TARGET_REPR_LENGTH = 255

MUTATING_METHODS = frozenset(["POST", "PUT", "PATCH", "DELETE"])

SENSITIVE_FIELD_PATTERN = re.compile(
    r"(password|secret|token|key|credential|auth|private|api_key|apikey|access_token"
    r"|refresh_token|bearer|authorization)",
    re.IGNORECASE,
)

_METHOD_TO_ACTION: dict[str, str] = {
    "POST": APIActivityAction.CREATE,
    "PUT": APIActivityAction.UPDATE,
    "PATCH": APIActivityAction.UPDATE,
    "DELETE": APIActivityAction.DELETE,
    "GET": APIActivityAction.READ,
    "HEAD": APIActivityAction.READ,
}


class APIActivityLogMiddleware:
    """Middleware to log mutating API activity to the APIActivityLog table.

    Captures all /api/v1/ POST/PUT/PATCH/DELETE calls regardless of status code
    (failed mutations are useful for spotting abuse). Also refreshes
    APIKey.last_used / last_used_ip when a key was used.
    """

    MODEL_MAPPINGS: dict[str, tuple[str, str]] = {
        "/api/v1/games/": ("srl", "games"),
        "/api/v1/categories/": ("srl", "categories"),
        "/api/v1/levels/": ("srl", "levels"),
        "/api/v1/players/": ("srl", "players"),
        "/api/v1/runs/": ("srl", "runs"),
        "/api/v1/platforms/": ("srl", "platforms"),
        "/api/v1/variables/": ("srl", "variables"),
    }

    def __init__(
        self,
        get_response: Callable[[HttpRequest], HttpResponse],
    ) -> None:
        self.get_response = get_response

    def __call__(
        self,
        request: HttpRequest,
    ) -> HttpResponse:
        response = self.get_response(request)
        self._update_api_key_usage(request)

        if request.path.startswith("/api/v1/") and request.method in MUTATING_METHODS:
            self._log_api_activity(request, response)

        return response

    def _update_api_key_usage(
        self,
        request: HttpRequest,
    ) -> None:
        api_key: APIKey | None = getattr(request, "api_key", None)
        if api_key is None:
            return
        try:
            APIKey.objects.filter(pk=api_key.pk).update(
                last_used=timezone.now(),
                last_used_ip=client_ip(request),
            )
        except Exception:
            logger.warning(
                "Failed to update API key last_used",
                exc_info=True,
                extra={"path": request.path, "key_id": api_key.pk},
            )

    def _log_api_activity(
        self,
        request: HttpRequest,
        response: HttpResponse,
    ) -> None:
        try:
            api_key_obj: APIKey | None = getattr(request, "api_key", None)
            user = getattr(request, "user", None)
            user_is_authed = bool(user and getattr(user, "is_authenticated", False))

            if api_key_obj is not None:
                auth_method = APIActivityAuthMethod.API_KEY
                user_id = api_key_obj.user_id
                key_label = api_key_obj.label or ""
            elif user_is_authed:
                auth_method = APIActivityAuthMethod.SESSION
                user_id = user.id  # type: ignore
                key_label = ""
            else:
                auth_method = APIActivityAuthMethod.ANONYMOUS
                user_id = None
                key_label = ""

            method = request.method or ""
            target_app, target_model, target_id, target_repr = self._extract_target(
                request,
            )

            ua = request.META.get("HTTP_USER_AGENT", "") or ""

            APIActivityLog.objects.create(
                user_id=user_id,
                api_key=api_key_obj,
                auth_method=auth_method,
                key_label_snapshot=key_label[:100],
                method=method[:8],
                path=request.path[:MAX_PATH_LENGTH],
                action=_METHOD_TO_ACTION.get(method, APIActivityAction.OTHER),
                status_code=response.status_code,
                ip=client_ip(request) or None,
                user_agent=ua[:MAX_USER_AGENT_LENGTH],
                target_app=target_app,
                target_model=target_model,
                target_id=target_id,
                target_repr=target_repr,
                change_summary=self._get_sanitized_body_summary(request),
            )

        except Exception as e:
            logger.warning(
                f"Failed to log API activity: {e}",
                exc_info=True,
                extra={"path": request.path, "method": request.method},
            )

    def _extract_target(
        self,
        request: HttpRequest,
    ) -> tuple[str, str, str, str]:
        path = request.path

        app_label = ""
        model_name = ""
        for path_prefix, (app, model) in self.MODEL_MAPPINGS.items():
            if path.startswith(path_prefix):
                app_label, model_name = app, model
                break

        if not app_label:
            return "", "", "", path[:MAX_TARGET_REPR_LENGTH]

        path_parts = [p for p in path.split("/") if p]
        object_id = ""
        if request.method == "POST":
            object_repr = f"New {model_name.title()}"
        elif len(path_parts) > 3:
            object_id = path_parts[3][:64]
            object_repr = f"{model_name.title()} {object_id}"
        else:
            object_repr = f"{model_name.title()} (bulk operation)"

        return app_label, model_name, object_id, object_repr[:MAX_TARGET_REPR_LENGTH]

    def _get_sanitized_body_summary(
        self,
        request: HttpRequest,
    ) -> dict[str, Any] | None:
        if not hasattr(request, "body") or not request.body:
            return None

        try:
            if len(request.body) > MAX_LOG_BODY_SIZE:
                return {"_truncated": True, "_size": len(request.body)}

            body = request.body.decode("utf-8")
            if len(body) > MAX_BODY_DISPLAY_LENGTH:
                return {"_truncated": True, "_size": len(body)}

            data = json.loads(body)
            if not isinstance(data, dict):
                return None

            safe_data = {
                key: value
                for key, value in data.items()
                if not SENSITIVE_FIELD_PATTERN.search(key)
            }

            return safe_data or None

        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            logger.debug(f"Could not parse request body for logging: {e}")
            return None
        except Exception as e:
            logger.warning(
                f"Failed to sanitize request body for logging: {e}",
                exc_info=True,
            )
            return None
