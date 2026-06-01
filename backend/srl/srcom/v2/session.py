import asyncio
import html
import json
import re
from datetime import datetime, timedelta, timezone
from typing import Optional

import sentry_sdk
from celery import shared_task
from django.conf import settings
from django_redis import get_redis_connection
from imap_tools import AND, MailBox
from speedruncompy.api import SpeedrunClient
from speedruncompy.endpoints import PutAuthLogin

_LOCK_KEY = "srcv2:bot_session:refresh"
_LOCK_TTL_SECONDS = 120


def _refresh_lock() -> "object":
    conn = get_redis_connection("default")
    return conn.lock(_LOCK_KEY, timeout=_LOCK_TTL_SECONDS, blocking_timeout=0)


def _within_cooldown() -> bool:
    from srl.models import BotSession

    bs = BotSession.load()
    if not bs.last_refresh_attempt_at:
        return False
    cooldown = timedelta(seconds=settings.SRC_BOT_REFRESH_COOLDOWN)
    return datetime.now(timezone.utc) - bs.last_refresh_attempt_at < cooldown


def _extract_2fa_code(
    text: str,
) -> Optional[str]:
    """Strips email (via IMAP) of HTML and extra stuff so we can extract JUST the 2FA."""
    raw = text or ""
    no_style = re.sub(
        r"<(?:style|script)[^>]*>.*?</(?:style|script)>",
        " ",
        raw,
        flags=re.IGNORECASE | re.DOTALL,
    )

    no_tags = re.sub(r"<[^>]+>", "", no_style)
    decoded = html.unescape(no_tags)
    cleaned = re.sub(r"\s+", " ", decoded).strip()

    anchored = re.search(
        r"\bcode\s+is[^A-Za-z0-9]{0,30}([A-Za-z0-9]{6})\b",
        cleaned,
        re.IGNORECASE,
    )
    if anchored:
        return anchored.group(1)

    # Fallback if all else fails
    for m in re.finditer(r"(?<!#)\b([A-Za-z0-9]{6})\b", cleaned):
        val = m.group(1)
        if re.search(r"\d", val):
            return val
    return None


def _fetch_2fa_code() -> Optional[str]:
    host = settings.SRC_BOT_MAILBOX_IMAP_HOST
    port = settings.SRC_BOT_MAILBOX_PORT
    user = settings.SRC_BOT_MAILBOX_USER
    pwd = settings.SRC_BOT_MAILBOX_APP_PASSWORD
    sender = settings.SRC_2FA_SENDER_EMAIL
    subject_pattern = re.compile(
        settings.SRC_2FA_SUBJECT_PATTERN,
        re.IGNORECASE,
    )
    timeout = settings.SRC_BOT_2FA_WAIT_TIMEOUT

    with MailBox(host, port=port).login(user, pwd) as box:
        box.idle.wait(timeout=timeout)
        candidates = list(
            box.fetch(
                AND(from_=sender, seen=False),
                reverse=True,
                limit=5,
            ),
        )
        for msg in candidates:
            if not subject_pattern.search(msg.subject or ""):
                continue
            body = msg.text or msg.html or ""
            code = _extract_2fa_code(body)
            if code:
                if msg.uid:
                    box.flag(msg.uid, "\\Seen", True)
                return code
        return None


@shared_task(name="srl.srcom.v2.refresh_bot_session")
def refresh_bot_session() -> None:
    from srl.models import BotSession

    lock = _refresh_lock()
    if not lock.acquire():
        return

    try:
        if _within_cooldown():
            return

        bs = BotSession.load()
        bs.status = BotSession.Status.REFRESHING
        bs.last_refresh_attempt_at = datetime.now(timezone.utc)
        bs.save(update_fields=["status", "last_refresh_attempt_at"])

        ua = settings.SRC_V2_USER_AGENT_SUFFIX
        client = SpeedrunClient(user_agent=ua)
        try:
            result = PutAuthLogin(
                settings.SRC_BOT_USERNAME,
                settings.SRC_BOT_PASSWORD,
                _client=client,
            ).perform_sync()

            if not result.loggedIn and getattr(result, "tokenChallengeSent", False):
                code = _fetch_2fa_code()
                if not code:
                    bs.status = BotSession.Status.LOCKED_OUT
                    bs.save(update_fields=["status"])
                    return
                result = PutAuthLogin(
                    settings.SRC_BOT_USERNAME,
                    settings.SRC_BOT_PASSWORD,
                    code,
                    _client=client,
                ).perform_sync()

            if not result.loggedIn:
                bs.status = BotSession.Status.LOCKED_OUT
                bs.save(update_fields=["status"])
                return

            # We only need the csrfToken from the response, and not the entire pydantic
            # validation from speedruncompy... this should be fine?
            raw_bytes, http_status = asyncio.run(
                client.POST("GetSession", {}),
            )
            if http_status != 200:
                bs.status = BotSession.Status.LOCKED_OUT
                bs.save(update_fields=["status"])
                return
            try:
                session_payload = json.loads(raw_bytes)
            except json.JSONDecodeError:
                bs.status = BotSession.Status.LOCKED_OUT
                bs.save(update_fields=["status"])
                return
            csrf = (session_payload.get("session", {}).get("csrfToken", "")) or ""
            if not csrf:
                bs.status = BotSession.Status.LOCKED_OUT
                bs.save(update_fields=["status"])
                return

            # speedruncompy's PHPSESSID property uses a filter, but it may return nothing...
            # so we gotta look into the jar directly to get it if nothing is returned.
            phpsessid = ""
            if client.cookie_jar is not None:
                for cookie in client.cookie_jar:
                    if cookie.key == "PHPSESSID":
                        phpsessid = cookie.value
                        break
            if not phpsessid:
                bs.status = BotSession.Status.LOCKED_OUT
                bs.save(update_fields=["status"])
                return
            bs.set_phpsessid(phpsessid)
            bs.csrf_token = csrf
            bs.validated_at = datetime.now(timezone.utc)
            bs.status = BotSession.Status.ACTIVE
            bs.consecutive_refresh_failures = 0
            update_fields = [
                "phpsessid_encrypted",
                "csrf_token",
                "validated_at",
                "status",
                "consecutive_refresh_failures",
            ]
            if bs.disabled_by_circuit_breaker:
                bs.disabled_by_circuit_breaker = False
                bs.v2_enabled_override = None
                update_fields += [
                    "disabled_by_circuit_breaker",
                    "v2_enabled_override",
                ]
            bs.save(update_fields=update_fields)
            if "v2_enabled_override" in update_fields:
                from srl.srcom.v2 import invalidate_v2_enabled_cache

                invalidate_v2_enabled_cache()
        except Exception as exc:
            bs.status = BotSession.Status.LOCKED_OUT
            bs.consecutive_refresh_failures = (bs.consecutive_refresh_failures or 0) + 1
            bs.save(
                update_fields=["status", "consecutive_refresh_failures"],
            )
            if bs.consecutive_refresh_failures >= 3:
                from srl.srcom.v2.errors import ErrorCategory

                trip_circuit_breaker(
                    reason=(f"3+ consecutive refresh_bot_session failures: " f"{exc}"),
                    category=ErrorCategory.AUTH,
                )
            raise
    finally:
        try:
            lock.release()
        except Exception:
            pass


def trip_circuit_breaker(
    reason: str,
    category: "object",
) -> None:
    """Auto-disable v2 in response to a severe failure and fires an alert to Sentry."""
    from srl.models import BotSession

    bs = BotSession.load()
    if bs.disabled_by_circuit_breaker:
        return

    bs.disabled_by_circuit_breaker = True
    bs.v2_enabled_override = False
    bs.last_severe_error_at = datetime.now(timezone.utc)
    bs.last_severe_error_category = str(category) if category else ""
    bs.save(
        update_fields=[
            "disabled_by_circuit_breaker",
            "v2_enabled_override",
            "last_severe_error_at",
            "last_severe_error_category",
        ],
    )
    from srl.srcom.v2 import invalidate_v2_enabled_cache

    invalidate_v2_enabled_cache()
    sentry_sdk.capture_message(
        f"SRC v2 circuit breaker tripped: {reason}",
        level="error",
    )
