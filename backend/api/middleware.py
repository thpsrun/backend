from __future__ import annotations

import json
import logging
import re
from collections.abc import Callable

from django.contrib.admin.models import ADDITION, CHANGE, DELETION, LogEntry
from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from django.http import HttpRequest, HttpResponse
from django.utils import timezone

from api.models import RoleAPIKey

logger = logging.getLogger(__name__)

User = get_user_model()

MAX_LOG_BODY_SIZE = 10000
MAX_BODY_DISPLAY_LENGTH = 500
MAX_USERNAME_LENGTH = 150
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

        if (
            request.path.startswith("/api/v1/")
            and request.method in MUTATING_METHODS
            and response.status_code < 400
        ):
            self._log_api_activity(request)

        return response

    def _log_api_activity(
        self,
        request: HttpRequest,
    ) -> None:
        """Log API activity to Django admin.

        Arguments:
            request: The incoming HTTP request.
        """
        try:
            api_key_obj = self._get_api_key_from_request(request)
            if not api_key_obj:
                return

            user_id = self._get_or_create_api_user(api_key_obj)
            if not user_id:
                return

            method = request.method
            if not method:
                return

            action_flag = self._get_action_flag(method)
            if not action_flag:
                return

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

    def _get_api_key_from_request(
        self,
        request: HttpRequest,
    ) -> RoleAPIKey | None:
        """Extract and validate the API key from the request headers.

        Arguments:
            request: The incoming HTTP request.

        Returns:
            The RoleAPIKey object if valid, None otherwise.
        """
        api_key_header = request.headers.get("X-API-Key")
        if not api_key_header:
            return None

        try:
            return RoleAPIKey.objects.get_from_key(api_key_header)
        except Exception as e:
            logger.warning(f"Failed to retrieve API key: {e}", exc_info=True)
            return None

    def _get_or_create_api_user(
        self,
        api_key: RoleAPIKey,
    ) -> int | None:
        """Get or create a Django User for the API key.

        Since API calls don't have traditional Django users, we create
        a special inactive user account for audit trail purposes.

        Arguments:
            api_key: The validated RoleAPIKey object.

        Returns:
            The user ID if successful, None otherwise.
        """
        try:
            sanitized_name = re.sub(r"[\s\-]+", "_", api_key.name)
            username = f"api_key_{sanitized_name}"[:MAX_USERNAME_LENGTH]

            user, _ = User.objects.get_or_create(
                username=username,
                defaults={
                    "first_name": "API Key",
                    "last_name": api_key.name[:30],
                    "email": f"{username}@api.thpsrun.local",
                    "is_active": False,
                    "is_staff": False,
                },
            )

            return user.id

        except Exception as e:
            logger.warning(f"Failed to get/create API user: {e}", exc_info=True)
            return None

    def _get_action_flag(self, method: str) -> int | None:
        """Convert HTTP method to Django admin action flag.

        Arguments:
            method: The HTTP method (POST, PUT, PATCH, DELETE).

        Returns:
            The corresponding Django admin action flag, or None if not mapped.
        """
        method_to_flag: dict[str, int] = {
            "POST": ADDITION,
            "PUT": CHANGE,
            "PATCH": CHANGE,
            "DELETE": DELETION,
        }
        return method_to_flag.get(method)

    def _extract_object_info(
        self,
        request: HttpRequest,
    ) -> tuple[ContentType, str | None, str] | None:
        """Extract object information from the API request.

        Arguments:
            request: The incoming HTTP request.

        Returns:
            Tuple of (ContentType, object_id, object_repr) or None if extraction fails.
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
        api_key: RoleAPIKey,
    ) -> str:
        """Create a descriptive change message for the log entry.

        Arguments:
            request: The incoming HTTP request.
            api_key: The validated RoleAPIKey object.

        Returns:
            A formatted change message string (max 255 chars).
        """
        try:
            method = request.method
            api_key_name = api_key.name

            method_messages: dict[str, str] = {
                "POST": f"Created via API (Key: {api_key_name})",
                "PUT": f"Updated via API (Key: {api_key_name})",
                "PATCH": f"Partially updated via API (Key: {api_key_name})",
                "DELETE": f"Deleted via API (Key: {api_key_name})",
            }

            base_message = method_messages.get(
                method or "",
                f"{method} via API (Key: {api_key_name})",
            )

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

    def _get_sanitized_body_summary(self, request: HttpRequest) -> str | None:
        """Extract and sanitize request body for logging.

        Filters out sensitive fields and truncates large payloads.

        Arguments:
            request: The incoming HTTP request.

        Returns:
            A sanitized JSON string of the body, or None if not applicable.
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
