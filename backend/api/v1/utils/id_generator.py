import secrets
import string
from collections.abc import Callable

ID_CHARS = string.ascii_lowercase + string.digits
ID_LENGTH = 8


def generate_id() -> str:
    """Generate a random alphanumeric ID.

    Returns:
        str: An 8-character lowercase alphanumeric ID.
    """
    return "".join(secrets.choice(ID_CHARS) for _ in range(ID_LENGTH))


def generate_unique_id(
    exists_check: Callable[[str], bool],
    max_attempts: int = 10,
) -> str:
    """Generate a unique ID, checking against existing records.

    Arguments:
        exists_check: A callable that returns True if the ID already exists.
        max_attempts: Maximum number of generation attempts before raising an error.

    Returns:
        str: A unique 8-character alphanumeric ID.
    """
    for _ in range(max_attempts):
        new_id = generate_id()
        if not exists_check(new_id):
            return new_id

    raise RuntimeError(
        f"Failed to generate unique ID after {max_attempts} attempts. "
        "This is extremely unlikely - please check for database issues."
    )


def get_or_generate_id(
    provided_id: str | None,
    exists_check: Callable[[str], bool],
) -> str:
    """Get the provided ID or generate a new one if not provided.

    If an ID is provided, validates it doesn't already exist. If no ID is provided, generates a new
    unique ID.

    Arguments:
        provided_id: The ID provided by the user, or None.
        exists_check: A callable that returns True if the ID already exists.

    Returns:
        str: Either the validated provided ID or a newly generated ID.
    """
    if provided_id is not None:
        if exists_check(provided_id):
            raise ValueError(f"ID '{provided_id}' already exists")
        return provided_id

    return generate_unique_id(exists_check)
