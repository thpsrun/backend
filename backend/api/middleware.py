from __future__ import annotations

import json
import logging
import re
from collections.abc import Callable

from django.contrib.admin.models import ADDITION, CHANGE, DELETION, LogEntry
from django.contrib.contenttypes.models import ContentType
from django.http import HttpRequest, HttpResponse
from django.utils import timezone

from api.client_ip import client_ip
from api.models import APIKey

logger = logging.getLogger(__name__)

MAX_LOG_BODY_SIZE = 10000
MAX_BODY_DISPLAY_LENGTH = 500
MAX_CHANGE_MESSAGE_LENGTH = 255

MUTATING_METHODS = frozenset(["POST", "PUT", "PATCH", "DELETE"])

SENSITIVE_FIELD_PATTERN = re.compile(
    r"(password|secret|token|key|credential|auth|private|api_key|apikey|access_token"
    r"|refresh_token|bearer|authorization)",
    re.IGNORECASE,
)


class APIActivityLogMiddleware:
    """Middleware to log API activities to Django admin Recent Actions.

    This captures API calls that modify data (POST, PUT, PATCH, DELETE) and
    creates LogEntry records so they appear in the Django admin's Recent Actions section.
    """

    MODEL_MAPPINGS: dict[str, str] = {
        "/api/v1/games/": "srl.games",
        "/api/v1/categories/": "srl.categories",
        "/api/v1/levels/": "srl.levels",
        "/api/v1/players/": "srl.players",
        "/api/v1/runs/": "srl.runs",
        "/api/v1/platforms/": "srl.platforms",
        "/api/v1/variables/": "srl.variables",
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

        if (
            request.path.startswith("/api/v1/")
            and request.method in MUTATING_METHODS
            and response.status_code < 400
        ):
            self._log_api_activity(request)

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
    ) -> None:
        """Log API activity to Django admin.

        Arguments:
            request: The incoming HTTP request.
        """
        try:
            api_key_obj: APIKey | None = getattr(request, "api_key", None)
            if not api_key_obj:
                return

            user_id = self._get_or_create_api_user(api_key_obj)
            if not user_id:
                return

            method = request.method
            if not method:
                return

            action_flag = self._get_action_flag(method)

            object_info = self._extract_object_info(request)
            if not object_info:
                return

            content_type, object_id, object_repr = object_info

            change_message = self._create_change_message(request, api_key_obj)

            LogEntry.objects.create(
                user_id=user_id,
                content_type=content_type,
                object_id=object_id,
                object_repr=object_repr,
                action_flag=action_flag,
                change_message=change_message,
                action_time=timezone.now(),
            )

        except Exception as e:
            logger.warning(
                f"Failed to log API activity: {e}",
                exc_info=True,
                extra={"path": request.path, "method": request.method},
            )

    def _get_or_create_api_user(
        self,
        api_key: APIKey,
    ) -> int | None:
        """Return the ID of the user who owns the API key.

        The new APIKey model is user-owned, so log entries attribute directly
        to the owning user instead of a synthetic "api_key_*" stand-in.
        """
        owner = getattr(api_key, "user", None)
        return owner.id if owner else None

    def _get_action_flag(
        self,
        method: str,
    ) -> int:
        """Convert HTTP method to Django admin action flag.

        Caller filters to MUTATING_METHODS, so method is always a key.
        """
        method_to_flag: dict[str, int] = {
            "POST": ADDITION,
            "PUT": CHANGE,
            "PATCH": CHANGE,
            "DELETE": DELETION,
        }
        return method_to_flag[method]

    def _extract_object_info(
        self,
        request: HttpRequest,
    ) -> tuple[ContentType, str | None, str] | None:
        """Extract object information from the API request.

        Arguments:
            request: The incoming HTTP request.

        Returns:
            Tuple: (ContentType, object_id, object_repr) or None if extraction fails.
        """
        try:
            path = request.path

            app_label: str | None = None
            model_name: str | None = None
            for path_prefix, model_path in self.MODEL_MAPPINGS.items():
                if path.startswith(path_prefix):
                    app_label, model_name = model_path.split(".")
                    break

            if not app_label or not model_name:
                return None

            try:
                content_type = ContentType.objects.get(
                    app_label=app_label,
                    model=model_name,
                )
            except ContentType.DoesNotExist:
                return None

            path_parts = [p for p in path.split("/") if p]

            if request.method == "POST":
                object_id = None
                object_repr = f"New {model_name.title()}"
            elif len(path_parts) > 3:
                object_id = path_parts[3]
                object_repr = f"{model_name.title()} {object_id}"
            else:
                object_id = None
                object_repr = f"{model_name.title()} (bulk operation)"

            return content_type, object_id, object_repr

        except Exception as e:
            logger.warning(
                f"Failed to extract object info from request: {e}",
                exc_info=True,
                extra={"path": request.path},
            )
            return None

    def _create_change_message(
        self,
        request: HttpRequest,
        api_key: APIKey,
    ) -> str:
        """Create a descriptive change message for the log entry.

        Arguments:
            request: The incoming HTTP request.
            api_key: The validated APIKey object.

        Returns:
            str: Formatted API key message.
        """
        try:
            method = request.method
            api_key_name = api_key.label

            method_messages: dict[str, str] = {
                "POST": f"Created via API (Key: {api_key_name})",
                "PUT": f"Updated via API (Key: {api_key_name})",
                "PATCH": f"Partially updated via API (Key: {api_key_name})",
                "DELETE": f"Deleted via API (Key: {api_key_name})",
            }

            base_message = method_messages[method or ""]

            body_summary = self._get_sanitized_body_summary(request)
            if body_summary:
                base_message += f" | Data: {body_summary}"

            return base_message[:MAX_CHANGE_MESSAGE_LENGTH]

        except Exception as e:
            logger.warning(
                f"Failed to create change message: {e}",
                exc_info=True,
                extra={"method": request.method},
            )
            return f"API {request.method} operation"

    def _get_sanitized_body_summary(
        self,
        request: HttpRequest,
    ) -> str | None:
        """Extract and sanitize request body for logging.

        Filters out sensitive fields and truncates large payloads.

        Arguments:
            request: The incoming HTTP request.

        Returns:
            json: A sanitized JSON string of the body, or None if not applicable.
        """
        if not hasattr(request, "body") or not request.body:
            return None

        try:
            if len(request.body) > MAX_LOG_BODY_SIZE:
                return "[Request body too large for logging]"

            body = request.body.decode("utf-8")
            if len(body) > MAX_BODY_DISPLAY_LENGTH:
                return None

            data = json.loads(body)
            if not isinstance(data, dict):
                return None

            safe_data = {
                key: value
                for key, value in data.items()
                if not SENSITIVE_FIELD_PATTERN.search(key)
            }

            if safe_data:
                return json.dumps(safe_data)

            return None

        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            logger.debug(f"Could not parse request body for logging: {e}")
            return None
        except Exception as e:
            logger.warning(
                f"Failed to sanitize request body for logging: {e}",
                exc_info=True,
            )
            return None
