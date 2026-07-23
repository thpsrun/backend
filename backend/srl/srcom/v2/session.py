import asyncio
import html
import json
import logging
import math
import re
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING, Optional

import sentry_sdk
from celery import shared_task
from django.conf import settings
from django_redis import get_redis_connection
from imap_tools import AND, MailBox
from speedruncompy.api import SpeedrunClient
from speedruncompy.endpoints import PutAuthLogin

from srl.srcom.v2 import is_v2_enabled

if TYPE_CHECKING:
    from srl.models import BotSession

logger = logging.getLogger(__name__)

_LOCK_KEY = "srcv2:bot_session:refresh"
_LOCK_TTL_SECONDS = 120


def _refresh_lock() -> "object":
    conn = get_redis_connection("default")
    return conn.lock(_LOCK_KEY, timeout=_LOCK_TTL_SECONDS, blocking_timeout=0)


def cooldown_remaining_seconds(
    bs: "BotSession | None" = None,
) -> int:
    """Seconds left before another bot-session refresh is permitted.

    Shared by the beat task (to decide whether to no-op) and the admin refresh endpoint (to tell the
    operator the queued task will be skipped for a bit).

    Arguments:
        bs (BotSession | None): An already-loaded session to re-use and check.

    Returns:
        remaining (int): Whole seconds (rounded up) until the refresh cooldown elapses, or 0
            when no cooldown is currently active.
    """
    if bs is None:
        from srl.models import BotSession

        bs = BotSession.load()
    if not bs.last_refresh_attempt_at:
        return 0
    elapsed = (datetime.now(timezone.utc) - bs.last_refresh_attempt_at).total_seconds()
    remaining = settings.SRC_BOT_REFRESH_COOLDOWN - elapsed
    return math.ceil(remaining) if remaining > 0 else 0


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


def _fetch_2fa_code() -> tuple[Optional[str], dict[str, int]]:
    """Fetch the SRC 2FA login code from the bot mailbox, with diagnostics.

    Returns:
        result (tuple[str | None, dict[str, int]]): The extracted 2FA code (None when none was
            found), paired with a diagnostics dict carrying the `unseen_fetched`,
            `subject_matched`, and `code_extracted` counts.
    """
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

    diag = {"unseen_fetched": 0, "subject_matched": 0, "code_extracted": 0}
    code: Optional[str] = None

    with MailBox(host, port=port).login(user, pwd) as box:
        box.idle.wait(timeout=timeout)
        candidates = list(
            box.fetch(
                AND(from_=sender, seen=False),
                reverse=True,
                limit=5,
            ),
        )
        diag["unseen_fetched"] = len(candidates)
        for msg in candidates:
            if not subject_pattern.search(msg.subject or ""):
                continue
            diag["subject_matched"] += 1
            body = msg.text or msg.html or ""
            extracted = _extract_2fa_code(body)
            if not extracted:
                continue
            diag["code_extracted"] += 1
            # Keep the first usable code and mark only that message Seen; the loop keeps going
            # purely so the diagnostic counts reflect the whole batch.
            if code is None:
                code = extracted
                if msg.uid:
                    box.flag(msg.uid, "\\Seen", True)

        if diag["unseen_fetched"] == 0:
            # No unseen sender mail at all is the exact shape of the July 2026 outage, so surface
            # recent sender metadata (never bodies) to tell a human-read code email apart from a
            # renamed subject line.
            for msg in box.fetch(
                AND(from_=sender),
                reverse=True,
                limit=5,
                mark_seen=False,
                headers_only=True,
            ):
                logger.warning(
                    "2FA mailbox recent message ignored: date=%s flags=%s subject=%r",
                    msg.date,
                    msg.flags,
                    msg.subject,
                )

    logger.info(
        "2FA mailbox scan: unseen_fetched=%d subject_matched=%d code_extracted=%d",
        diag["unseen_fetched"],
        diag["subject_matched"],
        diag["code_extracted"],
    )
    return code, diag


def _record_refresh_failure(
    bs: "BotSession",
    stage: str,
) -> None:
    """Record a soft (non-exception) refresh failure and trip the breaker at 3.

    Arguments:
        bs (BotSession): The singleton session row to mark LOCKED_OUT and bump.
        stage (str): Short name of the failing stage, surfaced in the breaker reason
            (e.g. `no_2fa_code`).
    """
    from srl.models import BotSession

    bs.status = BotSession.Status.LOCKED_OUT
    bs.consecutive_refresh_failures = (bs.consecutive_refresh_failures or 0) + 1
    bs.save(update_fields=["status", "consecutive_refresh_failures"])
    if bs.consecutive_refresh_failures >= 3:
        from srl.srcom.v2.errors import ErrorCategory

        trip_circuit_breaker(
            reason=(f"3+ consecutive refresh_bot_session failures at stage '{stage}'"),
            category=ErrorCategory.AUTH,
        )


@shared_task(name="srl.srcom.v2.refresh_bot_session")
def refresh_bot_session() -> None:
    """Re-login the SRC bot account and refresh the shared v2 session."""
    from srl.models import BotSession

    lock = _refresh_lock()
    if not lock.acquire():
        logger.info(
            "refresh_bot_session skipped: another refresh is already in progress.",
        )
        return

    try:
        remaining = cooldown_remaining_seconds()
        if remaining > 0:
            logger.info(
                "refresh_bot_session skipped: within cooldown, %d s remaining "
                "(SRC_BOT_REFRESH_COOLDOWN=%d s)",
                remaining,
                settings.SRC_BOT_REFRESH_COOLDOWN,
            )
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

            token_challenge_sent = getattr(result, "tokenChallengeSent", False)
            if not result.loggedIn and token_challenge_sent:
                code, mailbox_diag = _fetch_2fa_code()
                if not code:
                    logger.warning(
                        "refresh_bot_session failed: no 2FA code found "
                        "(unseen_fetched=%d subject_matched=%d code_extracted=%d)",
                        mailbox_diag["unseen_fetched"],
                        mailbox_diag["subject_matched"],
                        mailbox_diag["code_extracted"],
                    )
                    _record_refresh_failure(bs, stage="no_2fa_code")
                    return
                result = PutAuthLogin(
                    settings.SRC_BOT_USERNAME,
                    settings.SRC_BOT_PASSWORD,
                    code,
                    _client=client,
                ).perform_sync()
                if not result.loggedIn:
                    logger.warning(
                        "refresh_bot_session failed: second login (with 2FA "
                        "code) returned loggedIn=false",
                    )
                    _record_refresh_failure(bs, stage="second_login_failed")
                    return
            elif not result.loggedIn:
                logger.warning(
                    "refresh_bot_session failed: first login returned "
                    "loggedIn=%s tokenChallengeSent=%s",
                    result.loggedIn,
                    token_challenge_sent,
                )
                _record_refresh_failure(bs, stage="first_login_no_challenge")
                return

            # We only need the csrfToken from the response, and not the entire pydantic
            # validation from speedruncompy... this should be fine?
            raw_bytes, http_status = asyncio.run(
                client.POST("GetSession", {}),
            )
            if http_status != 200:
                logger.warning(
                    "refresh_bot_session failed: GetSession returned HTTP %s",
                    http_status,
                )
                _record_refresh_failure(bs, stage="getsession_http")
                return
            try:
                session_payload = json.loads(raw_bytes)
            except json.JSONDecodeError:
                logger.warning(
                    "refresh_bot_session failed: GetSession response was not "
                    "valid JSON",
                )
                _record_refresh_failure(bs, stage="getsession_json_decode")
                return
            csrf = (session_payload.get("session", {}).get("csrfToken", "")) or ""
            if not csrf:
                logger.warning(
                    "refresh_bot_session failed: GetSession response had an "
                    "empty csrfToken",
                )
                _record_refresh_failure(bs, stage="empty_csrf")
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
                logger.warning(
                    "refresh_bot_session failed: no PHPSESSID cookie in the "
                    "session cookie jar",
                )
                _record_refresh_failure(bs, stage="missing_phpsessid")
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
            logger.info(
                "refresh_bot_session succeeded: bot session ACTIVE, "
                "consecutive_refresh_failures reset to 0",
            )
        except Exception as exc:
            bs.status = BotSession.Status.LOCKED_OUT
            bs.consecutive_refresh_failures = (bs.consecutive_refresh_failures or 0) + 1
            bs.save(
                update_fields=["status", "consecutive_refresh_failures"],
            )
            logger.exception(
                "refresh_bot_session failed with an unexpected exception "
                "(consecutive_refresh_failures=%d)",
                bs.consecutive_refresh_failures,
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


@shared_task(name="srl.srcom.v2.keepalive_bot_session")
def keepalive_bot_session() -> None:
    """Periodically re-establish the bot session before it lapses."""
    from srl.models import BotSession

    if not is_v2_enabled():
        logger.debug("keepalive_bot_session: v2 disabled, nothing to do")
        return

    bs = BotSession.load()
    if bs.status == BotSession.Status.REFRESHING:
        logger.debug(
            "keepalive_bot_session: a refresh is already in progress "
            "(status REFRESHING), leaving it alone",
        )
        return

    if bs.status == BotSession.Status.ACTIVE and bs.validated_at is not None:
        ttl = timedelta(hours=settings.SRC_BOT_SESSION_TTL_HOURS)
        if datetime.now(timezone.utc) - bs.validated_at < ttl:
            logger.debug(
                "keepalive_bot_session: session still fresh (validated_at "
                "within SRC_BOT_SESSION_TTL_HOURS=%d h), skipping",
                settings.SRC_BOT_SESSION_TTL_HOURS,
            )
            return

    # refresh_bot_session is Redis-locked and cooldown-gated, so this is safe to fire on every
    # tick; it no-ops when a refresh already ran recently.
    logger.info(
        "keepalive_bot_session: session stale or unusable (status=%s), "
        "queueing refresh_bot_session",
        bs.status,
    )
    refresh_bot_session.delay()


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
