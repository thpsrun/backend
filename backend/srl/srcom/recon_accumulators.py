import json
from dataclasses import dataclass

from django_redis import get_redis_connection


ACCUMULATOR_TTL_SECONDS = 6 * 3600


@dataclass(frozen=True)
class VariantKey:
    game: str
    category: str
    level: str | None
    variables_hash: str


def _players_key(
    job_id: str,
) -> str:
    return f"recon:{job_id}:players"


def _variants_key(
    job_id: str,
) -> str:
    return f"recon:{job_id}:variants"


def _decode(
    value: bytes | str,
) -> str:
    return value.decode() if isinstance(value, bytes) else value


def _variant_to_str(
    variant: VariantKey,
) -> str:
    return json.dumps(
        [variant.game, variant.category, variant.level, variant.variables_hash],
    )


def _str_to_variant(
    payload: str,
) -> VariantKey:
    game, category, level, variables_hash = json.loads(payload)
    return VariantKey(
        game=game,
        category=category,
        level=level,
        variables_hash=variables_hash,
    )


def add_affected_player(
    job_id: str | None,
    player_id: str,
) -> None:
    if not job_id:
        return
    conn = get_redis_connection("default")
    key = _players_key(job_id)
    conn.sadd(key, player_id)
    conn.expire(key, ACCUMULATOR_TTL_SECONDS)


def get_affected_players(
    job_id: str,
) -> set[str]:
    conn = get_redis_connection("default")
    raw = conn.smembers(_players_key(job_id))
    return {_decode(x) for x in raw}


def add_affected_variant(
    job_id: str | None,
    variant: VariantKey,
) -> None:
    if not job_id:
        return
    conn = get_redis_connection("default")
    key = _variants_key(job_id)
    conn.sadd(key, _variant_to_str(variant))
    conn.expire(key, ACCUMULATOR_TTL_SECONDS)


def get_affected_variants(
    job_id: str,
) -> set[VariantKey]:
    conn = get_redis_connection("default")
    raw = conn.smembers(_variants_key(job_id))
    return {_str_to_variant(_decode(x)) for x in raw}


def clear_accumulators(
    job_id: str,
) -> None:
    conn = get_redis_connection("default")
    conn.delete(_players_key(job_id), _variants_key(job_id))
