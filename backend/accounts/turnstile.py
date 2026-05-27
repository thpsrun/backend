import logging

import requests
from django.conf import settings

logger = logging.getLogger("accounts.turnstile")


class TurnstileUnavailable(Exception):
    """Raised when Cloudflare's siteverify endpoint cannot be reached or returns garbage."""


def verify_turnstile(
    token: str,
    remote_ip: str | None,
) -> bool:
    data: dict[str, str] = {
        "secret": settings.TURNSTILE_SECRET_KEY,
        "response": token,
    }
    if remote_ip:
        data["remoteip"] = remote_ip
    try:
        response = requests.post(
            settings.TURNSTILE_VERIFY_URL,
            data=data,
            timeout=settings.TURNSTILE_TIMEOUT_SECONDS,
        )
    except requests.RequestException as exc:
        logger.exception("turnstile siteverify request failed")
        raise TurnstileUnavailable(str(exc)) from exc

    if response.status_code != 200:
        logger.error(
            "turnstile siteverify returned non-200",
            extra={"status_code": response.status_code},
        )
        raise TurnstileUnavailable(f"status_code={response.status_code}")

    try:
        body: dict[str, object] = response.json()
    except ValueError as exc:
        logger.exception("turnstile siteverify returned non-JSON body")
        raise TurnstileUnavailable("invalid json") from exc

    success = bool(body.get("success"))
    if not success:
        logger.warning(
            "turnstile siteverify rejected token",
            extra={"error_codes": body.get("error-codes")},
        )
    return success
