import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from srl.models import Runs

ARCH_URL_TEMPLATE = "https://archive.thps.run/videos/{run_id}.mp4"


class Command(BaseCommand):
    help = (
        "Link archived B2 videos to runs by setting Runs.arch_video from an rclone lsjson "
        "listing."
    )

    def add_arguments(
        self,
        parser,
    ) -> None:
        parser.add_argument(
            "--file",
            required=True,
            help="Path to the rclone lsjson output (e.g. b2_videos.json).",
        )
        parser.add_argument(
            "--apply",
            action="store_true",
            help="Persist changes. Without this flag the command only reports.",
        )
        parser.add_argument(
            "--overwrite",
            action="store_true",
            help="Also replace runs that already have a different arch_video set.",
        )

    def handle(
        self,
        *args,
        **options,
    ) -> None:
        file_path: Path = Path(options["file"])
        apply_changes: bool = options["apply"]
        overwrite: bool = options["overwrite"]
        prefix: str = "" if apply_changes else "DRY RUN: "

        if not file_path.is_file():
            raise CommandError(f"File not found: {file_path}")

        try:
            entries = json.loads(file_path.read_text())
        except json.JSONDecodeError as exc:
            raise CommandError(f"Could not parse JSON from {file_path}: {exc}")

        if not isinstance(entries, list):
            raise CommandError("Expected a JSON array from rclone lsjson output.")

        archived: dict[str, str] = {}
        ignored: int = 0
        for entry in entries:
            name: str = entry.get("Name") or entry.get("Path") or ""
            if not name.endswith(".mp4"):
                ignored += 1
                continue
            run_id: str = name.removesuffix(".mp4")
            if not run_id:
                ignored += 1
                continue
            archived[run_id] = ARCH_URL_TEMPLATE.format(run_id=run_id)

        archived_ids: set[str] = set(archived)
        self.stdout.write(
            f"{prefix}Read {len(entries)} entries -> {len(archived_ids)} unique video IDs."
        )
        if ignored:
            self.stdout.write(
                self.style.WARNING(f"Ignored {ignored} entries without a .mp4 name.")
            )

        existing_ids: set[str] = set(
            Runs.objects.filter(pk__in=archived_ids).values_list("pk", flat=True)
        )
        orphan_count: int = len(archived_ids - existing_ids)

        to_update: list[Runs] = []
        already_set: int = 0
        run_qs = Runs.objects.filter(pk__in=existing_ids).only("id", "arch_video")
        for run in run_qs.iterator(chunk_size=1000):
            url: str = archived[run.id]
            if run.arch_video:
                if not overwrite or run.arch_video == url:
                    already_set += 1
                    continue
            run.arch_video = url
            to_update.append(run)

        self.stdout.write(f"{prefix}Matched runs:          {len(existing_ids)}")
        self.stdout.write(f"{prefix}Will set arch_video:   {len(to_update)}")
        skipped_msg: str = f"{prefix}Skipped (already set): {already_set}"
        if not overwrite:
            skipped_msg += " [use --overwrite to replace]"
        self.stdout.write(skipped_msg)
        self.stdout.write(f"{prefix}Orphan archives:       {orphan_count}")

        if not apply_changes:
            self.stdout.write(
                self.style.NOTICE(
                    "Dry run; no changes written. Re-run with --apply to persist."
                )
            )
            return

        if not to_update:
            self.stdout.write(self.style.SUCCESS("Nothing to update."))
            return

        with transaction.atomic():
            Runs.objects.bulk_update(
                to_update,
                ["arch_video"],
                batch_size=500,
            )

        self.stdout.write(
            self.style.SUCCESS(f"Set arch_video on {len(to_update)} runs.")
        )
