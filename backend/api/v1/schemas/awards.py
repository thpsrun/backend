from pydantic import ConfigDict, Field

from api.v1.schemas.base import BaseEmbedSchema


class AwardListSchema(BaseEmbedSchema):
    """Base schema for `Awards` data when listed as a standalone resource.

    Attributes:
        id (int): Unique ID of the award.
        name (str): Award name.
        description (str | None): Award description.
        image (str | None): Award image URL.
    """

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "id": 1,
                "name": "Sub-1 Club",
                "description": "Awarded for setting a sub-1-minute time.",
                "image": "/media/awards/sub1.png",
            },
        },
    )

    id: int
    name: str = Field(..., max_length=50)
    description: str | None = Field(default=None, max_length=500)
    image: str | None = None
