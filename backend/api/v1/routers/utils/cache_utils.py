import hashlib
from typing import Any, Callable

from django.core.cache import caches
from django.db.models import Max, Q
from guides.models import Guides
from srl.models import Categories, Levels, Players, Runs, Variables, VariableValues


def leaderboard_cache_key(
    game_id: str,
    category_id: str,
    level_id: str | None = None,
) -> str:
    filters: dict[str, str] = {
        "game_id": game_id,
        "category_id": category_id,
    }

    if level_id is not None:
        filters["level_id"] = level_id

    latest = Runs.objects.filter(**filters).aggregate(
        latest=Max(
            "updated_at",
        )
    )["latest"]

    timestamp = latest.isoformat() if latest else "None"

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
    latest = Runs.objects.filter(
        obsolete=False,
        vid_status="verified",
    ).aggregate(latest=Max("updated_at"),)["latest"]

    timestamp = latest.isoformat() if latest else "None"

    return f"leaderboard:overall:{timestamp}"


def game_leaderboard_cache_key(
    game_id: str,
) -> str:
    latest = Runs.objects.filter(
        game_id=game_id,
        obsolete=False,
        vid_status="verified",
    ).aggregate(latest=Max("updated_at"),)["latest"]

    timestamp = latest.isoformat() if latest else "None"

    return f"leaderboard:game:{game_id}:{timestamp}"


def player_cache_key(
    user_id: str,
) -> str:
    latest = Runs.objects.filter(run_players__player__id=user_id).aggregate(
        latest=Max("updated_at")
    )["latest"]

    timestamp = latest.isoformat() if latest else "None"

    return f"player_stats:{user_id}:{timestamp}"


def wr_cache_key(
    game_id: str,
    category_id: str,
    level_id: str | None = None,
) -> str:
    filters = {
        "game_id": game_id,
        "cat_id": category_id,
        "place": 1,
        "obsolete": False,
    }

    if level_id is not None:
        filters["level_id"] = level_id

    latest = Runs.objects.filter(**filters).aggregate(latest=Max("updated_at"))[
        "latest"
    ]

    timestamp = latest.isoformat() if latest else "None"

    return f"wr:game:{game_id}:cat:{category_id}:level{level_id}:{timestamp}"


def main_wrs_cache_key() -> str:
    latest = Runs.objects.filter(
        place=1,
        obsolete=False,
        vid_status="verified",
    ).aggregate(latest=Max("updated_at"),)["latest"]

    timestamp = latest.isoformat() if latest else "None"

    return f"main:wrs:{timestamp}"


def main_pbs_cache_key() -> str:
    latest = Runs.objects.filter(
        place__gt=1,
        obsolete=False,
        vid_status="verified",
    ).aggregate(latest=Max("updated_at"),)["latest"]

    timestamp = latest.isoformat() if latest else "None"

    return f"main:pbs:{timestamp}"


def main_records_cache_key() -> str:
    run_latest = Runs.objects.filter(
        place=1,
        obsolete=False,
        runtype="main",
        category__appear_on_main=True,
        vid_status="verified",
    ).aggregate(latest=Max("updated_at"),)["latest"]

    cat_latest = Categories.objects.filter(
        appear_on_main=True,
    ).aggregate(
        latest=Max("updated_at"),
    )["latest"]

    vv_latest = VariableValues.objects.aggregate(
        latest=Max("updated_at"),
    )["latest"]

    timestamps = [t for t in [run_latest, cat_latest, vv_latest] if t is not None]
    latest = max(timestamps) if timestamps else None
    timestamp = latest.isoformat() if latest else "None"

    return f"main:records:{timestamp}"


def main_players_runs_cache_key(
    player: str,
) -> str:
    player_data = Players.objects.get(
        Q(id__iexact=player) | Q(name__iexact=player) | Q(nickname__iexact=player)
    ).id

    latest_runs = Runs.objects.filter(
        run_players__player=player_data,
        vid_status="verified",
    ).aggregate(latest=Max("updated_at"),)["latest"]

    timestamp = latest_runs.isoformat() if latest_runs else "None"

    return f"player:runs:{timestamp}"


def game_categories_cache_key(
    game_id: str,
) -> str:
    cat_latest = Categories.objects.filter(
        game_id=game_id,
    ).aggregate(
        latest=Max("updated_at"),
    )["latest"]

    var_latest = Variables.objects.filter(
        Q(game_id=game_id) | Q(cat__game_id=game_id),
    ).aggregate(latest=Max("updated_at"),)["latest"]

    timestamps = [t for t in [cat_latest, var_latest] if t is not None]
    latest = max(timestamps) if timestamps else None
    timestamp = latest.isoformat() if latest else "None"

    return f"game:{game_id}:categories:{timestamp}"


def game_levels_cache_key(
    game_id: str,
) -> str:
    level_latest = Levels.objects.filter(
        game_id=game_id,
    ).aggregate(
        latest=Max("updated_at"),
    )["latest"]

    var_latest = Variables.objects.filter(
        level__game_id=game_id,
    ).aggregate(
        latest=Max("updated_at"),
    )["latest"]

    timestamps = [t for t in [level_latest, var_latest] if t is not None]
    latest = max(timestamps) if timestamps else None
    timestamp = latest.isoformat() if latest else "None"

    return f"game:{game_id}:levels:{timestamp}"


def run_cache_key(
    run_id: str,
) -> str:
    latest = Runs.objects.filter(id=run_id).aggregate(
        latest=Max("updated_at"),
    )["latest"]

    timestamp = latest.isoformat() if latest else "None"

    return f"run:{run_id}:{timestamp}"


def guide_cache_key(
    guide_id: int,
) -> str:
    latest = Guides.objects.filter(id=guide_id).aggregate(
        latest=Max("updated_at"),
    )["latest"]

    timestamp = latest.isoformat() if latest else "None"

    return f"guide:{guide_id}:{timestamp}"


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
