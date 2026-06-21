from unittest.mock import MagicMock, patch

from api.v1.routers.auth.bot_session import post_refresh
from django.test import RequestFactory, TestCase


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
