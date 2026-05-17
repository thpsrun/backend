from datetime import datetime
from typing import Any, Literal, Self

from django.conf import settings
from pydantic import BaseModel, ConfigDict, Field, field_serializer, model_validator

RunTypeType = Literal["main", "il"]
RunStatusType = Literal["verified", "new", "rejected"]
CategoryTypeType = Literal["per-level", "per-game"]
VariableScopeType = Literal["global", "full-game", "all-levels", "single-level"]
TimingMethodType = Literal["rta", "lrt", "igt"]


class ErrorResponse(BaseModel):
    """Standardized error response schema for the API.

    Attributes:
        error (str): Error message sent to the client.
        details (dict[str, Any] | None): Additional details related to the error.
    """

    error: str
    details: dict[str, Any] | None = None

    _SENSITIVE_KEYS: set[str] = {"exception", "type"}

    # This is an additional feature added that helps seamlessly keep exception errors in
    # development, but strip them in production since `details` could provide sensitive
    # data on the environment in some cases.
    @model_validator(mode="after")
    def strip_exception_details_in_production(
        self,
    ) -> Self:
        if not settings.DEBUG and self.details:
            for key in self._SENSITIVE_KEYS:
                self.details.pop(key, None)
            if not self.details:
                self.details = None
        return self


class ValidationErrorResponse(BaseModel):
    """Validation error response schema for the API.

    Used when requested data fails validation with field-specific error details.

    Attributes:
        error (str): Error message sent to the client.
        validation_errors (dict[str, Any]): Field-specific validation errors.
    """

    error: str = Field(default="Validation failed")
    validation_errors: list[dict[str, Any]]


class BaseEmbedSchema(BaseModel):
    model_config = ConfigDict(
        from_attributes=True,
        arbitrary_types_allowed=True,
    )


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
    def serialize_datetime(
        cls,
        value: datetime | None,
    ) -> str | None:
        return value.isoformat() if value else None


class SlugMixin(BaseModel):
    """Pydantic mixin for models with generated slugs.

    Attributes:
        name (str): Human-readable name of an object.
        slug (str): URL-friendly name of the object.
    """

    name: str
    slug: str = Field(..., description="URL-friendly slug", min_length=1, max_length=30)


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
