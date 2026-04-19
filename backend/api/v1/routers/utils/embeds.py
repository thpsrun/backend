from srl.models.categories import Categories
from srl.models.games import Games
from srl.models.levels import Levels

from api.v1.schemas.base import VALID_EMBEDS, validate_embeds


class InvalidEmbedsError(Exception):
    """Raised when `?embed=...` contains values not in `VALID_EMBEDS[resource]`."""

    def __init__(
        self,
        invalid: list[str],
        valid: set[str],
    ) -> None:
        self.invalid: list[str] = invalid
        self.valid: set[str] = valid
        super().__init__(f"Invalid embed(s): {', '.join(invalid)}")


def parse_embeds(
    embed: str | None,
    resource: str,
) -> list[str]:
    """Parse a `?embed=a,b` query string and validate against the resource registry.

    Raises `InvalidEmbedsError` if any requested embed is not allowed on the resource.
    The Ninja exception handler registered on the API turns this into a 400 response.
    """
    if not embed:
        return []
    embeds = [e.strip() for e in embed.split(",") if e.strip()]
    invalid = validate_embeds(resource, embeds)
    if invalid:
        raise InvalidEmbedsError(
            invalid=invalid,
            valid=VALID_EMBEDS.get(resource, set()),
        )
    return embeds


def serialize_game_embed(
    game: Games,
) -> dict:
    """Standard embed payload for a `Games` instance."""
    return {
        "id": game.id,
        "name": game.name,
        "slug": game.slug,
        "release": game.release.isoformat() if game.release else None,
        "boxart": game.boxart,
        "twitch": game.twitch,
        "defaulttime": game.defaulttime,
        "idefaulttime": game.idefaulttime,
        "pointsmax": game.pointsmax,
        "ipointsmax": game.ipointsmax,
    }


def serialize_category_embed(
    category: Categories,
) -> dict:
    """Standard embed payload for a `Categories` instance."""
    return {
        "id": category.id,
        "name": category.name,
        "slug": category.slug,
        "type": category.type,
        "url": category.url,
        "rules": category.rules,
        "appear_on_main": category.appear_on_main,
        "archive": category.archive,
    }


def serialize_level_embed(
    level: Levels,
) -> dict:
    """Standard embed payload for a `Levels` instance."""
    return {
        "id": level.id,
        "name": level.name,
        "slug": level.slug,
        "url": level.url,
        "rules": level.rules,
    }
