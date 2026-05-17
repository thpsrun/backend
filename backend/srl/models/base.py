from django.core.exceptions import ValidationError
from django.db import models
from django.db.models.fields.files import ImageFieldFile


class LeaderboardChoices(models.TextChoices):
    REALTIME = "rta", "RTA"
    REALTIME_NOLOADS = "lrt", "LRT"
    INGAME = "igt", "IGT"


def all_methods_default() -> list[str]:
    return [
        LeaderboardChoices.REALTIME,
        LeaderboardChoices.REALTIME_NOLOADS,
        LeaderboardChoices.INGAME,
    ]


METHOD_TO_TIME_FIELD: dict[str, str] = {
    LeaderboardChoices.REALTIME.value: "time_secs",
    LeaderboardChoices.REALTIME_NOLOADS.value: "timenl_secs",
    LeaderboardChoices.INGAME.value: "timeigt_secs",
}


TIMING_FALLBACK_PRIORITY: list[str] = [
    LeaderboardChoices.REALTIME.value,
    LeaderboardChoices.INGAME.value,
    LeaderboardChoices.REALTIME_NOLOADS.value,
]


def validate_award_image(
    image: ImageFieldFile,
) -> None:
    file_size = image.file.size
    if file_size > 3 * 1024 * 1024:
        raise ValidationError("Max size of file is 3 MB")

    file_width = image.file.image._size[0]
    file_height = image.file.image._size[1]
    if file_width != file_height:
        raise ValidationError(
            f"File width/height must match. Current: {file_width}x{file_height}"
        )


def validate_flag_image(
    image: ImageFieldFile,
) -> None:
    file_size = image.file.size
    if file_size > 3 * 1024 * 1024:
        raise ValidationError("Max size of file is 3 MB")

    file_width = image.file.image._size[0]
    file_height = image.file.image._size[1]
    actual_ratio = file_width / file_height
    if abs(actual_ratio - 1.5) > 0.01:
        raise ValidationError(
            f"Aspect ratio must be 1.5. "
            f"Current: {file_width}x{file_height} ({actual_ratio:.2f})"
        )


def validate_profile_bg(
    image: ImageFieldFile,
) -> None:
    file_size = image.file.size
    if file_size > 10 * 1024 * 1024:
        raise ValidationError("Max size of file is 10 MB")
