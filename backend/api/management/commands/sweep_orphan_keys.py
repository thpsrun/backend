from __future__ import annotations

import logging
from argparse import ArgumentParser
from typing import Any

from django.core.management.base import BaseCommand

from api.backability import is_key_backable
from api.models import APIKey, APIKeyRevokedReason

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Revoke any active APIKey that the owner can no longer back."

    def add_arguments(self, parser: ArgumentParser) -> None:
        parser.add_argument(
            "--dry-run",
            action="store_true",
            default=False,
        )

    def handle(self, *args: Any, **options: Any) -> None:
        dry_run: bool = options["dry_run"]
        revoked = 0
        for key in APIKey.objects.filter(revoked=False).iterator():
            if is_key_backable(key):
                continue
            if dry_run:
                self.stdout.write(
                    f"DRY-RUN would revoke id={key.pk} "
                    f"user={key.user_id} label={key.label!r}",
                )
            else:
                key.revoked = True
                key.revoked_reason = APIKeyRevokedReason.PERMISSION_REVOKED
                key.save(update_fields=["revoked", "revoked_reason"])
                logger.info(
                    "sweep revoked key id=%s user=%s",
                    key.pk,
                    key.user_id,
                )
            revoked += 1
        self.stdout.write(
            self.style.SUCCESS(f"sweep complete; revoked {revoked} key(s)."),
        )
