from typing import Any

from django.core.exceptions import ValidationError
from django.db import models
from django.db.models.fields.files import ImageFieldFile


class LeaderboardChoices(models.TextChoices):
    REALTIME = "rta", "RTA"
    REALTIME_NOLOADS = "lrt", "LRT"
    INGAME = "igt", "IGT"


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


def all_methods_default() -> list[str]:
    return [
        LeaderboardChoices.REALTIME,
        LeaderboardChoices.REALTIME_NOLOADS,
        LeaderboardChoices.INGAME,
    ]


def validate_allowed_subset(
    instance: Any,
    parent_allowed: list[str] | None,
    parent_primary: str | None,
    child_relation_name: str,
    child_allowed_attr: str = "required_methods",
    child_id_attr: str = "id",
) -> None:
    """Validate `instance` required_methods/defaulttime against its parent's window
    and ensure none of its children's required_methods escape this instance's window.

    Raises ValidationError if any constraint fails. Shared by Categories,
    Variables, and VariableValues `clean()` implementations.

    Arguments:
        instance (Any): The model being validated. Must expose `required_methods`,
            `defaulttime`, and `pk`.
        parent_allowed (list[str] | None): The resolved parent's methods (or None for inherit).
        parent_primary (str | None): The resolved parent's primary timing method (or None).
        child_relation_name (str): Reverse manager name on `instance` (e.g.
            "variables_set", "variablevalues_set").
        child_allowed_attr (str): Attribute on the child holding the narrowed list.
        child_id_attr (str): Attribute on the child to surface in error messages.
    """
    errors: dict = {}
    required_methods = getattr(instance, "required_methods", None)
    defaulttime = getattr(instance, "defaulttime", None)

    if required_methods is not None:
        if len(required_methods) == 0:
            errors["required_methods"] = "Cannot be an empty list; use null to inherit."
        elif parent_allowed is not None and not set(required_methods) <= set(
            parent_allowed,
        ):
            errors["required_methods"] = (
                f"Must be a subset of the parent's allowed methods "
                f"({list(parent_allowed)})."
            )
        elif (
            defaulttime is None
            and parent_primary is not None
            and parent_primary not in required_methods
        ):
            errors["defaulttime"] = (
                f"Inherited primary ({parent_primary}) is not in the narrowed "
                f"required_methods; set defaulttime explicitly."
            )

    if defaulttime is not None:
        effective_allowed = required_methods or parent_allowed
        if effective_allowed is not None and defaulttime not in effective_allowed:
            errors["defaulttime"] = (
                f"defaulttime ({defaulttime}) must be one of required_methods "
                f"({list(effective_allowed)})."
            )

    if instance.pk and required_methods is not None and child_relation_name:
        allowed_set = set(required_methods)
        manager = getattr(instance, child_relation_name, None)
        if manager is not None:
            filter_kwargs = {f"{child_allowed_attr}__isnull": False}
            children = manager.filter(**filter_kwargs)
            offenders = [
                getattr(child, child_id_attr)
                for child in children
                if not set(getattr(child, child_allowed_attr)).issubset(allowed_set)
            ]
            if offenders:
                errors["required_methods"] = (
                    f"Cannot narrow: children rely on removed methods. "
                    f"Offending ids: {offenders}"
                )

    # Validate any children's defaulttime is still in this instance's effective allowed window.
    effective_window = required_methods or parent_allowed
    if instance.pk and effective_window is not None and child_relation_name:
        manager = getattr(instance, child_relation_name, None)
        if manager is not None:
            children = manager.filter(defaulttime__isnull=False)
            window_set = set(effective_window)
            bad_default = [
                getattr(child, child_id_attr)
                for child in children
                if child.defaulttime not in window_set
            ]
            if bad_default:
                errors.setdefault("required_methods", "")
                msg = (
                    f"Cannot narrow: children have defaulttime outside the new "
                    f"window. Offending ids: {bad_default}"
                )
                if errors["required_methods"]:
                    errors["required_methods"] = f"{errors['required_methods']} {msg}"
                else:
                    errors["required_methods"] = msg

    if errors:
        raise ValidationError(errors)


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
