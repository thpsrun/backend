from typing import Any

from django.conf import settings
from speedruncompy.api import SpeedrunClient
from speedruncompy.endpoints import PutRunSettings
from speedruncompy.exceptions import Forbidden

from srl.srcom.v2.errors import ErrorCategory, map_exception


class SrcV2Error(Exception):
    """Base for v2 client errors. Always carries a category."""

    def __init__(
        self,
        message: str,
        category: ErrorCategory,
        original: BaseException | None = None,
    ) -> None:
        super().__init__(message)
        self.category = category
        self.original = original


class SrcV2AuthError(SrcV2Error):
    """401 Unauthorized: stale PHPSESSID. Refresh + retry is appropriate."""

    pass


class SrcV2PermissionError(SrcV2Error):
    """403 Forbidden: account lacks moderator status on this game.

    Refreshing the bot session will not fix this. Tasks hitting this
    should fail terminally and surface to admins (likely the bot has
    been removed as a moderator on the run's game).
    """

    pass


class SrcV2RateLimited(SrcV2Error):
    pass


class SrcV2ContractError(SrcV2Error):
    pass


class SrcV2ValidationError(SrcV2Error):
    pass


class SrcV2NetworkError(SrcV2Error):
    pass


class SrcV2ServerError(SrcV2Error):
    pass


class SrcV2UnknownError(SrcV2Error):
    pass


_CATEGORY_TO_EXC: dict[ErrorCategory, type[SrcV2Error]] = {
    ErrorCategory.AUTH: SrcV2AuthError,
    ErrorCategory.RATE_LIMIT: SrcV2RateLimited,
    ErrorCategory.API_CONTRACT: SrcV2ContractError,
    ErrorCategory.VALIDATION: SrcV2ValidationError,
    ErrorCategory.NETWORK: SrcV2NetworkError,
    ErrorCategory.API_SERVER: SrcV2ServerError,
    ErrorCategory.UNKNOWN: SrcV2UnknownError,
    ErrorCategory.MAILBOX: SrcV2UnknownError,
}


class SrcV2Client:
    """Wraps a single speedruncompy SpeedrunClient for the edit-run flow."""

    def __init__(
        self,
    ) -> None:
        from srl.models import BotSession

        bs = BotSession.load()
        ua_suffix = getattr(settings, "SRC_V2_USER_AGENT_SUFFIX", "thps.run-bot")
        self._inner = SpeedrunClient(user_agent=ua_suffix)
        sess = bs.get_phpsessid()
        if sess:
            self._inner.PHPSESSID = sess
        self._csrf_default = bs.csrf_token

    def put_run_settings(
        self,
        settings_payload: dict[str, Any],
        csrf_token: str | None = None,
    ) -> Any:
        token = csrf_token or self._csrf_default
        try:
            return PutRunSettings(
                csrfToken=token,
                settings=settings_payload,
                autoverify=False,
                _client=self._inner,
            ).perform_sync()
        except BaseException as exc:
            category = map_exception(exc)
            if isinstance(exc, Forbidden):
                raise SrcV2PermissionError(
                    str(exc),
                    category=category,
                    original=exc,
                ) from exc
            cls = _CATEGORY_TO_EXC.get(category, SrcV2UnknownError)
            raise cls(str(exc), category=category, original=exc) from exc
