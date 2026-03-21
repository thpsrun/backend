from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, field_serializer

RunTypeType = Literal["main", "il"]
RunStatusType = Literal["verified", "new", "rejected"]
CategoryTypeType = Literal["per-level", "per-game"]
VariableScopeType = Literal["global", "full-game", "all-levels", "single-level"]
LeaderboardTimeType = Literal["realtime", "realtime_noloads", "ingame"]


class ErrorResponse(BaseModel):
    """Standardized error response schema for the API.

    Attributes:
        error (str): Error message sent to the client.
        details (dict[str, Any] | None): Additional details related to the error.
    """

    error: str
    details: dict[str, Any] | None = None


class ValidationErrorResponse(BaseModel):
    """Validation error response schema for the API.

    Used when requested data fails validation with field-specific error details.

    Attributes:
        error (str): Error message sent to the client.
        validation_errors (dict[str, Any]): Field-specific validation errors.
    """

    error: str = Field(default="Validation failed")
    validation_errors: dict[str, list[str]]


class PaginatedResponse(BaseModel):
    """Standardized pagination response schema for the API.

    Attributes:
        count (int): Total number of items being returned.
        next (str | None): URL for the next page.
        previous (str | None): URL for previous page.
        results (List[Dict[str, Any]]): Actual data being returned.
    """

    count: int
    next: str | None = None
    previous: str | None = None
    results: list[dict[str, Any]]


class BaseEmbedSchema(BaseModel):
    class Config:
        from_attributes = True
        arbitrary_types_allowed = True
        exclude_none = False


class TimestampMixin(BaseModel):
    """Pydantic mixin for models with timestamp fields.

    Standardizes timestamp handling and ensures ISO format serialization.

    Attributes:
        created_at (datetime | None): When the object was created.
        updated_at (datetime | None): When the object was last updated.
    """

    created_at: datetime | None = None
    updated_at: datetime | None = None

    @field_serializer("created_at", "updated_at")
    @classmethod
    def serialize_datetime(cls, value: datetime | None) -> str | None:
        return value.isoformat() if value else None


class SlugMixin(BaseModel):
    """Pydantic mixin for models with generated slugs.

    Attributes:
        name (str): Human-readable name of an object.
        slug (str): URL-friendly name of the object.
    """

    name: str
    slug: str = Field(..., description="URL-friendly slug", min_length=1, max_length=15)


VALID_EMBEDS: dict[str, set[str]] = {
    "games": {"categories", "levels", "platforms"},
    "categories": {"game", "variables", "values"},
    "levels": {"game", "variables", "values"},
    "variables": {"game", "category", "level", "values"},
    "players": {"country", "stats", "awards", "runs", "profile", "profile-obsolete"},
    "runs": {"game", "category", "level", "variables"},
    "guides": {"game", "tags"},
    "tags": set(),
}


def validate_embeds(
    endpoint: str,
    embeds: list[str],
) -> list[str]:
    """Validation to ensure requested embeds are allowed on the endpoint.

    Arguments:
        endpoint (str): API endpoint name.
        embeds (List[str]): List of requested embed fields.

    Returns:
        List[str]: List of invalid embeds; empty if all valid.
    """
    valid_for_endpoint: set[str] = VALID_EMBEDS.get(endpoint, set())
    return [embed for embed in embeds if embed not in valid_for_endpoint]
