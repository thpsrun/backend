from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from api.v1.routers.auth.bot_session import post_refresh
from django.test import RequestFactory, TestCase, override_settings
from srl.models import BotSession
from srl.srcom.v2.session import cooldown_remaining_seconds


class CooldownRemainingSecondsTest(TestCase):
    """Regression tests for cooldown_remaining_seconds' self-loading (no-bs) path."""

    def test_loads_singleton_when_bs_omitted(
        self,
    ) -> None:
        """Called with no bs (the Celery refresh_bot_session path), it must load the
        singleton itself rather than raising NameError.

        Regression for THPS-RUN-DEV-28: BotSession was only imported under TYPE_CHECKING,
        so the no-argument branch (bs is None -> BotSession.load()) blew up with
        NameError at runtime whenever the beat task invoked it.
        """
        bs = BotSession.load()
        bs.last_refresh_attempt_at = None
        bs.save(update_fields=["last_refresh_attempt_at"])

        self.assertEqual(cooldown_remaining_seconds(), 0)

    @override_settings(SRC_BOT_REFRESH_COOLDOWN=30)
    def test_loads_singleton_and_reports_active_cooldown(
        self,
    ) -> None:
        """The self-loading path also returns the live remaining cooldown, not just 0."""
        bs = BotSession.load()
        bs.last_refresh_attempt_at = datetime.now(timezone.utc)
        bs.save(update_fields=["last_refresh_attempt_at"])

        remaining = cooldown_remaining_seconds()

        self.assertGreater(remaining, 0)
        self.assertLessEqual(remaining, 30)


class BotSessionRefreshEndpointTest(TestCase):
    """Regression tests for the POST /admin/bot-session/refresh dispatch path."""

    def setUp(
        self,
    ) -> None:
        """Build a request factory for direct view invocation."""
        self.factory = RequestFactory()

    @patch("api.v1.routers.auth.bot_session.refresh_bot_session")
    def test_refresh_endpoint_dispatches_task_asynchronously(
        self,
        mock_task: MagicMock,
    ) -> None:
        """The refresh view must enqueue the Celery task, never run it inline.

        Running refresh_bot_session() synchronously inside a gunicorn worker blocks on the up-to-90s
        IMAP 2FA wait (SRC_BOT_2FA_WAIT_TIMEOUT), which exceeds gunicorn's 30s default worker
        timeout and gets the worker before it can complete.
        """
        request = self.factory.post("/api/v1/auth/admin/bot-session/refresh")

        post_refresh(request)

        mock_task.delay.assert_called_once_with()
        mock_task.assert_not_called()

    @patch("api.v1.routers.auth.bot_session.refresh_bot_session")
    def test_refresh_response_reports_queued_without_cooldown(
        self,
        mock_task: MagicMock,
    ) -> None:
        """With no prior attempt, the response says queued and no cooldown."""
        bs = BotSession.load()
        bs.last_refresh_attempt_at = None
        bs.save(update_fields=["last_refresh_attempt_at"])
        request = self.factory.post("/api/v1/auth/admin/bot-session/refresh")

        result = post_refresh(request)

        self.assertEqual(result.status_code, 200)
        self.assertTrue(result.value.refresh_queued)
        self.assertIsNone(result.value.cooldown_seconds_remaining)

    @override_settings(SRC_BOT_REFRESH_COOLDOWN=30)
    @patch("api.v1.routers.auth.bot_session.refresh_bot_session")
    def test_refresh_response_reports_active_cooldown(
        self,
        mock_task: MagicMock,
    ) -> None:
        """A recent attempt surfaces the remaining cooldown seconds."""
        bs = BotSession.load()
        bs.last_refresh_attempt_at = datetime.now(timezone.utc)
        bs.save(update_fields=["last_refresh_attempt_at"])
        request = self.factory.post("/api/v1/auth/admin/bot-session/refresh")

        result = post_refresh(request)

        self.assertTrue(result.value.refresh_queued)
        self.assertIsNotNone(result.value.cooldown_seconds_remaining)
        self.assertGreater(result.value.cooldown_seconds_remaining, 0)
        self.assertLessEqual(result.value.cooldown_seconds_remaining, 30)
