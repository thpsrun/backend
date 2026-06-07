import hashlib
from typing import Any, Callable

from accounts.models import CustomUser
from django.core.cache import caches
from django.db.models import Max, Min, Q, QuerySet
from django.utils import timezone
from guides.models import Guides
from nav.models import NavItem, SocialLink
from srl.models import (
    Categories,
    Games,
    Levels,
    Players,
    RunHistory,
    Runs,
    Variables,
    VariableValues,
)

_TS_TTL = 30  # seconds to cache timestamp lookups
_HISTORY_CACHE_PREFIX = "pointslb:history"
_HISTORY_CURRENT_YEAR_TTL = 60 * 60 * 24


def _cached_timestamp(
    ts_key: str,
    queryset: QuerySet | list[QuerySet],
    cache_name: str = "default",
) -> str:
    cache = caches[cache_name]
    timestamp = cache.get(ts_key)
    if timestamp is None:
        querysets = queryset if isinstance(queryset, list) else [queryset]
        latest_values = [
            qs.aggregate(latest=Max("updated_at"))["latest"] for qs in querysets
        ]
        latest_values = [v for v in latest_values if v is not None]
        latest = max(latest_values) if latest_values else None
        timestamp = latest.isoformat() if latest else "None"
        cache.set(ts_key, timestamp, timeout=_TS_TTL)
    return timestamp


def _timing_config_querysets(
    game_id: str,
    category_id: str | None = None,
) -> list[QuerySet]:
    """Timing-config tables whose updated_at should bust leaderboard caches."""
    if category_id is not None:
        categories = Categories.objects.filter(id=category_id)
    else:
        categories = Categories.objects.filter(game_id=game_id)
    return [
        Games.objects.filter(id=game_id),
        categories,
        Variables.objects.filter(game_id=game_id),
        VariableValues.objects.filter(var__game_id=game_id),
    ]


def _player_display_querysets(
    *,
    game_id: str | None = None,
    player_id: str | None = None,
    run_id: str | None = None,
) -> list[QuerySet]:
    """Player + linked-user rows whose `updated_at` must bust caches that embed player display data.

    Scope to the players a given cache can embed; pass nothing for global boards
    that may show any player. Scoping is a safe superset (it never excludes a
    player a board shows), so over-invalidation is acceptable but staleness is
    not.

    Arguments:
        game_id (str | None): Restrict to players who have a run in this game.
        player_id (str | None): Restrict to a single player.
        run_id (str | None): Restrict to players who appear on this run.

    Returns:
        list[QuerySet]: ``[players_qs, users_qs]`` for `_cached_timestamp`.
    """
    players = Players.objects.all()
    users = CustomUser.objects.filter(player__isnull=False)

    if game_id is not None:
        players = players.filter(player_runs__run__game_id=game_id)
        users = users.filter(player__player_runs__run__game_id=game_id)
    if player_id is not None:
        players = players.filter(id=player_id)
        users = users.filter(player__id=player_id)
    if run_id is not None:
        players = players.filter(player_runs__run_id=run_id)
        users = users.filter(player__player_runs__run_id=run_id)

    return [players, users]


def leaderboard_cache_key(
    game_id: str,
    category_id: str,
    level_id: str | None = None,
) -> str:
    filters: dict[str, Any] = {
        "game_id": game_id,
        "category_id": category_id,
        "obsolete": False,
        "vid_status": "verified",
    }

    if level_id is not None:
        filters["level_id"] = level_id

    timestamp = _cached_timestamp(
        f"ts:lb:{game_id}:{category_id}:{level_id}",
        [
            Runs.objects.filter(**filters),
            *_timing_config_querysets(game_id, category_id=category_id),
            *_player_display_querysets(game_id=game_id),
        ],
    )

    cache_key = [
        f"game:{game_id}",
        f"category:{category_id}",
        f"level:{level_id}" if level_id else "FG",
        f"timestamp:{timestamp}",
    ]

    cache_string = ":".join(cache_key)

    key = hashlib.md5(cache_string.encode()).hexdigest()

    return f"lb:{key}:{timestamp[:10]}"


def overall_leaderboard_cache_key() -> str:
    timestamp = _cached_timestamp(
        "ts:lb:overall",
        [
            Runs.objects.filter(obsolete=False, vid_status="verified"),
            *_player_display_querysets(),
        ],
    )

    return f"leaderboard:overall:{timestamp}"


def game_leaderboard_cache_key(
    game_id: str,
) -> str:
    timestamp = _cached_timestamp(
        f"ts:lb:game:{game_id}",
        [
            Runs.objects.filter(
                game_id=game_id,
                obsolete=False,
                vid_status="verified",
            ),
            *_timing_config_querysets(game_id),
            *_player_display_querysets(game_id=game_id),
        ],
    )

    return f"leaderboard:game:{game_id}:{timestamp}"


def player_cache_key(
    user_id: str,
) -> str:
    timestamp = _cached_timestamp(
        f"ts:player:{user_id}",
        [
            Runs.objects.filter(run_players__player__id=user_id),
            *_player_display_querysets(player_id=user_id),
        ],
    )

    return f"player_stats:{user_id}:{timestamp}"


def wr_cache_key(
    game_id: str,
    category_id: str,
    level_id: str | None = None,
) -> str:
    filters: dict[str, Any] = {
        "game_id": game_id,
        "category_id": category_id,
        "place": 1,
        "obsolete": False,
    }

    if level_id is not None:
        filters["level_id"] = level_id

    timestamp = _cached_timestamp(
        f"ts:wr:{game_id}:{category_id}:{level_id}",
        [
            Runs.objects.filter(**filters),
            *_player_display_querysets(game_id=game_id),
        ],
    )

    return f"wr:game:{game_id}:cat:{category_id}:level{level_id}:{timestamp}"


def main_wrs_cache_key() -> str:
    timestamp = _cached_timestamp(
        "ts:main:wrs",
        [
            Runs.objects.filter(place=1, obsolete=False, vid_status="verified"),
            *_player_display_querysets(),
        ],
    )

    return f"main:wrs:{timestamp}"


def main_pbs_cache_key() -> str:
    timestamp = _cached_timestamp(
        "ts:main:pbs",
        [
            Runs.objects.filter(place__gt=1, obsolete=False, vid_status="verified"),
            *_player_display_querysets(),
        ],
    )

    return f"main:pbs:{timestamp}"


def main_records_cache_key() -> str:
    run_ts = _cached_timestamp(
        "ts:main:records:runs",
        [
            Runs.objects.filter(
                place=1,
                obsolete=False,
                runtype="main",
                category__appear_on_main=True,
                vid_status="verified",
            ),
            *_player_display_querysets(),
        ],
    )

    cat_ts = _cached_timestamp(
        "ts:main:records:cats",
        Categories.objects.filter(appear_on_main=True),
    )

    vv_ts = _cached_timestamp(
        "ts:main:records:vv",
        VariableValues.objects.all(),
    )

    timestamps = [t for t in [run_ts, cat_ts, vv_ts] if t != "None"]
    timestamp = max(timestamps) if timestamps else "None"

    return f"main:record:{timestamp}"


def main_stats_cache_key() -> str:
    timestamp = _cached_timestamp(
        "ts:main:stats",
        Runs.objects.filter(vid_status="verified"),
    )

    return f"main:stats:{timestamp}"


def main_players_runs_cache_key(
    player: str,
) -> str:
    player_obj = Players.objects.filter(
        Q(id__iexact=player) | Q(name__iexact=player) | Q(nickname__iexact=player)
    ).first()
    player_data = player_obj.id if player_obj else player

    timestamp = _cached_timestamp(
        f"ts:player:runs:{player_data}",
        [
            Runs.objects.filter(
                run_players__player=player_data,
                vid_status="verified",
            ),
            *_player_display_querysets(player_id=player_data),
        ],
    )

    return f"player:runs:{player_data}:{timestamp}"


def game_categories_cache_key(
    game_id: str,
) -> str:
    cat_ts = _cached_timestamp(
        f"ts:game:cats:{game_id}",
        Categories.objects.filter(game_id=game_id),
    )

    var_ts = _cached_timestamp(
        f"ts:game:cats:vars:{game_id}",
        Variables.objects.filter(
            Q(game_id=game_id) | Q(cat__game_id=game_id),
        ),
    )

    timestamps = [t for t in [cat_ts, var_ts] if t != "None"]
    timestamp = max(timestamps) if timestamps else "None"

    return f"game:{game_id}:categories:{timestamp}"


def game_levels_cache_key(
    game_id: str,
) -> str:
    level_ts = _cached_timestamp(
        f"ts:game:levels:{game_id}",
        Levels.objects.filter(game_id=game_id),
    )

    var_ts = _cached_timestamp(
        f"ts:game:levels:vars:{game_id}",
        Variables.objects.filter(level__game_id=game_id),
    )

    timestamps = [t for t in [level_ts, var_ts] if t != "None"]
    timestamp = max(timestamps) if timestamps else "None"

    return f"game:{game_id}:levels:{timestamp}"


def run_cache_key(
    run_id: str,
) -> str:
    timestamp = _cached_timestamp(
        f"ts:run:{run_id}",
        [
            Runs.objects.filter(id=run_id),
            *_player_display_querysets(run_id=run_id),
        ],
    )

    return f"run:{run_id}:{timestamp}"


def guide_cache_key(
    guide_id: int,
) -> str:
    timestamp = _cached_timestamp(
        f"ts:guide:{guide_id}",
        Guides.objects.filter(id=guide_id),
    )

    return f"guide:{guide_id}:{timestamp}"


def lbs_runs_cache_key(
    game_id: str,
    category_id: str,
    value_slugs: list[str] | None = None,
) -> str:
    timestamp = _cached_timestamp(
        f"ts:lbs:runs:{game_id}:{category_id}",
        [
            Runs.objects.filter(
                game_id=game_id,
                category_id=category_id,
                obsolete=False,
                vid_status="verified",
            ),
            *_timing_config_querysets(game_id, category_id=category_id),
            *_player_display_querysets(game_id=game_id),
        ],
    )

    values_str = ",".join(sorted(value_slugs)) if value_slugs else "all"
    raw = f"lbs:{game_id}:{category_id}:{values_str}:{timestamp}"
    key = hashlib.md5(raw.encode()).hexdigest()

    return f"lbs:runs:{key}:{timestamp[:10]}"


def lbs_game_stats_cache_key(
    game_id: str,
) -> str:
    timestamp = _cached_timestamp(
        f"ts:lbs:stats:{game_id}",
        [
            Runs.objects.filter(
                game_id=game_id,
                obsolete=False,
                vid_status="verified",
            ),
            *_timing_config_querysets(game_id),
        ],
    )

    return f"lbs:stats:{game_id}:{timestamp}"


def lbs_game_recent_cache_key(
    game_id: str,
) -> str:
    timestamp = _cached_timestamp(
        f"ts:lbs:recent:{game_id}",
        [
            Runs.objects.filter(
                game_id=game_id,
                obsolete=False,
                vid_status="verified",
            ),
            *_timing_config_querysets(game_id),
            *_player_display_querysets(game_id=game_id),
        ],
    )

    return f"lbs:recent:{game_id}:{timestamp}"


def lbs_il_summary_cache_key(
    game_id: str,
    value_slugs: list[str] | None = None,
) -> str:
    timestamp = _cached_timestamp(
        f"ts:lbs:il_summary:{game_id}",
        [
            Runs.objects.filter(
                game_id=game_id,
                runtype="il",
                obsolete=False,
                vid_status="verified",
            ),
            *_timing_config_querysets(game_id),
            *_player_display_querysets(game_id=game_id),
        ],
    )

    values_str = ",".join(sorted(value_slugs)) if value_slugs else ""

    return f"lbs:il_summary:{game_id}:{values_str}:{timestamp}"


def lbs_il_runs_cache_key(
    game_id: str,
    level_id: str,
    category_id: str,
    value_slugs: list[str] | None = None,
) -> str:
    timestamp = _cached_timestamp(
        f"ts:lbs:il:{game_id}:{level_id}:{category_id}",
        [
            Runs.objects.filter(
                game_id=game_id,
                level_id=level_id,
                category_id=category_id,
                obsolete=False,
                vid_status="verified",
            ),
            *_timing_config_querysets(game_id, category_id=category_id),
            *_player_display_querysets(game_id=game_id),
        ],
    )

    values_str = ",".join(sorted(value_slugs)) if value_slugs else "all"
    raw = f"lbs:il:{game_id}:{level_id}:{category_id}:{values_str}:{timestamp}"
    key = hashlib.md5(raw.encode()).hexdigest()

    return f"lbs:il_runs:{key}:{timestamp[:10]}"


def check_cache_query(
    cache_key: str,
    query: Callable,
    timeout: int | None = None,
    cache_name: str = "default",
) -> Any:
    cache = caches[cache_name]

    cache_result = cache.get(cache_key)

    if cache_result is not None:
        return cache_result

    result = query()

    cache.set(cache_key, result, timeout=timeout)

    return result


def navbar_cache_key() -> str:
    """Cache key for the navbar endpoint, based on latest update across both models."""
    nav_ts = _cached_timestamp(
        "ts:navbar:nav",
        NavItem.objects.all(),
    )
    social_ts = _cached_timestamp(
        "ts:navbar:social",
        SocialLink.objects.all(),
    )

    timestamps = [t for t in (nav_ts, social_ts) if t != "None"]
    if timestamps:
        timestamp = max(timestamps)
    else:
        timestamp = "empty"

    return f"navbar:{timestamp}"


def history_cache_key(
    game_id: str,
    category_id: str,
    level_id: str | None = None,
    value_slugs: list[str] | None = None,
) -> str:
    filters: dict[str, Any] = {
        "game_id": game_id,
        "category_id": category_id,
        "vid_status": "verified",
    }
    if level_id is not None:
        filters["level_id"] = level_id

    timestamp = _cached_timestamp(
        f"ts:history:{game_id}:{category_id}:{level_id}",
        [
            Runs.objects.filter(**filters),
            *_player_display_querysets(game_id=game_id),
        ],
    )

    values_str = ",".join(sorted(value_slugs)) if value_slugs else "all"
    raw = f"history:{game_id}:{category_id}:{level_id}:{values_str}:{timestamp}"
    key = hashlib.md5(raw.encode()).hexdigest()

    return f"history:{key}:{timestamp[:10]}"


def historical_cache_key(
    scope: str,
    mode: str,
    year: int,
    month: int,
) -> str:
    return f"{_HISTORY_CACHE_PREFIX}:{scope}:{mode}:{year}-{month:02d}"


def historical_cache_ttl(
    year: int,
) -> int | None:
    current_year = timezone.now().year
    if year < current_year:
        return None
    return _HISTORY_CURRENT_YEAR_TTL


HISTORY_EARLIEST_TTL = 60 * 60 * 24


def get_earliest_possible(
    game_id: str | None = None,
) -> str | None:
    cache_scope = game_id if game_id else "all"
    cache_key = f"{_HISTORY_CACHE_PREFIX}:earliest:{cache_scope}"
    cache = caches["default"]

    cached = cache.get(cache_key)
    if cached is not None:
        return cached if cached != "__NONE__" else None

    qs = RunHistory.objects.all()
    if game_id:
        qs = qs.filter(run__game_id=game_id)

    earliest_dt = qs.aggregate(Min("start_date"))["start_date__min"]

    if earliest_dt is None:
        cache.set(cache_key, "__NONE__", timeout=HISTORY_EARLIEST_TTL)
        return None

    result = earliest_dt.strftime("%Y-%m")
    cache.set(cache_key, result, timeout=HISTORY_EARLIEST_TTL)
    return result
