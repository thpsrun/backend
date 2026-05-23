from __future__ import annotations

from typing import Any

from django.core.signals import request_finished
from django.dispatch import receiver

from auditlog.context import clear_actor


@receiver(
    request_finished,
    dispatch_uid="auditlog.signals._clear_actor_on_request_finished",
)
def _clear_actor_on_request_finished(
    sender: Any,
    **kwargs: Any,
) -> None:
    clear_actor()
