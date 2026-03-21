from datetime import date as date_type
from typing import Any

from django.core.cache import caches
from django.db.models import Q, QuerySet, Sum
from django.db.models.functions import TruncDate
from srl.models import Players, RunPlayers, Runs

from api.v1.routers.utils import (
    main_pbs_cache_key,
    main_records_cache_key,
    main_stats,
    main_wrs_cache_key,
)
from api.v1.schemas.runs import PlayerRunEmbedSchema


def compute_run_subcategory(
    run: Runs,
) -> str | None:
    """Compute the subcategory display string from a run's prefetched RunVariableValues.

    Requires the queryset to have:
        .select_related("category", "level")
        .prefetch_related("runvariablevalues_set__value")
    """
    level = getattr(run, "level", None)
    category = getattr(run, "category", None)
    if level:
        base = getattr(level, "name", "") or ""
    elif category:
        base = getattr(category, "name", "") or ""
    else:
        base = ""

    try:
        rvvs = list(run.runvariablevalues_set.all())  # type: ignore
        rvvs_sorted = sorted(rvvs, key=lambda x: x.variable_id)
        values = [rvv.value.name for rvv in rvvs_sorted]
    except Exception:
        values = []

    if values:
        return f"{base} ({', '.join(values)})"
    return base or None


def player_data_export(
    run_players: "QuerySet[RunPlayers]",
) -> list[dict[str, str | None]]:
    players = [
        {
            "name": rp.player.nickname if rp.player.nickname else rp.player.name,
            "country": rp.player.countrycode.name if rp.player.countrycode else None,
        }
        for rp in run_players
    ]

    return players if players else [{"name": "Anonymous", "country": None}]


def record_player_data_export(
    run_players: "QuerySet[RunPlayers]",
    run_url: str,
    run_video: str | None,
    run_arch_video: str | None,
    run_date: str | None,
) -> list[dict[str, Any]]:
    players = [
        {
            "player": {
                "name": rp.player.nickname if rp.player.nickname else rp.player.name,
                "country": (
                    rp.player.countrycode.name if rp.player.countrycode else None
                ),
            },
            "video": run_video,
            "arch_video": run_arch_video,
            "src_url": run_url,
            "date": run_date,
        }
        for rp in run_players
    ]

    if not players:
        players = [
            {
                "player": {"name": "Anonymous", "country": None},
                "url": run_url,
                "date": run_date,
            }
        ]

    return players


def query_latest_runs(
    wr: bool = True,
) -> list[dict[str, Any]]:
    filters = {
        "obsolete": False,
        "v_date__isnull": False,
        "vid_status": "verified",
    }

    if wr:
        filters["place"] = 1
    else:
        filters["place__gt"] = 1

    runs: QuerySet[Runs] = (
        Runs.objects.select_related("game", "category", "level")
        .prefetch_related(
            "run_players__player__countrycode",
            "runvariablevalues_set__value",
        )
        .filter(**filters)
        .order_by("-v_date")[:5]
    )

    result = []
    for run in runs:
        players_data = player_data_export(run.run_players.all())  # type: ignore
        result.append(
            {
                "id": run.id,
                "game": {"name": run.game.name},
                "subcategory": compute_run_subcategory(run),
                "players": players_data,
                "time": run.p_time,
                "date": run.v_date.isoformat() if run.v_date else None,
                "video": run.video,
                "url": run.url,
            }
        )

    return result


def query_records() -> list[dict[str, Any]]:
    runs: list[Runs] = list(
        Runs.objects.select_related("game", "category", "level")
        .prefetch_related(
            "run_players__player__countrycode",
            "runvariablevalues_set__value",
        )
        .filter(
            runtype="main",
            place=1,
            obsolete=False,
            vid_status="verified",
            category__appear_on_main=True,
        )
        .exclude(
            runvariablevalues__value__appear_on_main=False,
        )
        .order_by("category__name")
        .annotate(o_date=TruncDate("date"))
    )

    grouped_runs: list[dict[str, Any]] = []
    seen_records: set[tuple[str, str | None, str | None]] = set()

    for run in runs:
        subcat = compute_run_subcategory(run)
        key = (run.game.slug, subcat, run.time)
        if key not in seen_records:
            grouped_runs.append(
                {
                    "game": {"name": run.game.name, "slug": run.game.slug},
                    "game_release": run.game.release,
                    "subcategory": subcat,
                    "time": run.time,
                    "players": [],
                }
            )
            seen_records.add(key)  # type: ignore

        for record in grouped_runs:
            if (
                record["game"]["slug"] == run.game.slug
                and record["subcategory"] == subcat
                and record["time"] == run.time
            ):
                record["players"].extend(
                    record_player_data_export(
                        run.run_players.all(),  # type: ignore
                        run.url,
                        run.video,
                        run.arch_video,
                        run.o_date.isoformat() if run.o_date else None,  # type: ignore
                    )
                )

    run_list = sorted(
        grouped_runs,
        key=lambda x: x["game_release"],
        reverse=False,
    )

    for record in run_list:
        del record["game_release"]

    return run_list


def query_stats() -> dict[str, Any]:
    run_count = Runs.objects.only("id").all().count()
    player_count = Players.objects.only("id").all().count()

    runs_with_vars = Runs.objects.prefetch_related(
        "runvariablevalues_set__value",
    ).filter(
        runvariablevalues__isnull=False,
    )
    subcat_count = len({compute_run_subcategory(r) for r in runs_with_vars} - {None})

    counts = {
        "runs": run_count,
        "subcategories": subcat_count,
        "players": player_count,
    }

    return counts


def query_player_runs(
    player_id: str,
    include_obsoletes: bool = False,
) -> list[dict[str, Any]]:
    qs: QuerySet[Runs] = (
        Runs.objects.select_related("game", "category", "level")
        .prefetch_related(
            "run_players__player__countrycode",
            "runvariablevalues_set__value",
        )
        .filter(
            run_players__player__id=player_id,
            vid_status="verified",
        )
    )

    if not include_obsoletes:
        qs = qs.filter(obsolete=False)

    qs = qs.order_by("game__release", "date")

    result = []
    for run in qs:
        data = PlayerRunEmbedSchema.model_validate(run).model_dump()
        data["players"] = player_data_export(run.run_players.all())  # type: ignore
        result.append(data)

    return result


def query_overall_leaderboard() -> list[dict[str, Any]]:
    rows = (
        RunPlayers.objects.filter(
            run__obsolete=False,
            run__vid_status="verified",
        )
        .values(
            "player_id",
            "player__name",
            "player__nickname",
            "player__url",
            "player__pfp",
        )
        .annotate(
            total_points=Sum("run__points"),
            fg_points=Sum("run__points", filter=Q(run__runtype="main")),
            il_points=Sum("run__points", filter=Q(run__runtype="il")),
        )
        .filter(total_points__gt=0)
        .order_by("-total_points")
    )

    result = []
    for i, row in enumerate(rows):
        nickname = row["player__nickname"]
        name = row["player__name"]
        result.append(
            {
                "rank": i + 1,
                "player_id": row["player_id"],
                "player_name": nickname if nickname else name,
                "player_url": row["player__url"],
                "player_pfp": row["player__pfp"],
                "total_points": row["total_points"] or 0,
                "fg_points": row["fg_points"] or 0,
                "il_points": row["il_points"] or 0,
            }
        )

    return result


def query_game_leaderboard(
    game_id: str,
    game_slug: str,
) -> list[dict[str, Any]]:
    qs = RunPlayers.objects.filter(
        run__obsolete=False,
        run__vid_status="verified",
        run__game_id=game_id,
    )

    if game_slug == "thps4":
        qs = qs.exclude(run__level__slug="zoo-feed-the-hippos")

    rows = (
        qs.values(
            "player_id",
            "player__name",
            "player__nickname",
            "player__url",
            "player__pfp",
        )
        .annotate(
            total_points=Sum("run__points"),
            fg_points=Sum("run__points", filter=Q(run__runtype="main")),
            il_points=Sum("run__points", filter=Q(run__runtype="il")),
        )
        .filter(total_points__gt=0)
        .order_by("-total_points")
    )

    result = []
    for i, row in enumerate(rows):
        nickname = row["player__nickname"]
        name = row["player__name"]
        result.append(
            {
                "rank": i + 1,
                "player_id": row["player_id"],
                "player_name": nickname if nickname else name,
                "player_url": row["player__url"],
                "player_pfp": row["player__pfp"],
                "total_points": row["total_points"] or 0,
                "fg_points": row["fg_points"] or 0,
                "il_points": row["il_points"] or 0,
            }
        )

    return result


def query_thps4_oldest_runs(
    game_id: str,
) -> list[dict[str, Any]]:
    runs: QuerySet[Runs] = (
        Runs.objects.select_related("game", "category", "level")
        .prefetch_related("run_players__player")
        .filter(
            game_id=game_id,
            obsolete=False,
            vid_status="verified",
        )
        .exclude(level__slug="zoo-feed-the-hippos")
        .order_by("date")
    )

    result = []
    for run in runs:
        all_rp = list(run.run_players.all())  # type: ignore
        rp = all_rp[0] if all_rp else None
        player = rp.player if rp else None
        if player and player.nickname:
            player_name = player.nickname
        elif player:
            player_name = player.name
        else:
            player_name = "Anonymous"

        days_held = (date_type.today() - run.date.date()).days if run.date else -1

        result.append(
            {
                "player_id": player.id if player else "",
                "player_name": player_name,
                "game_name": run.game.name,
                "game_slug": run.game.slug,
                "category_name": run.category.name if run.category else None,
                "level_name": run.level.name if run.level else None,
                "place": run.place,
                "time": run.p_time,
                "date": run.date,
                "days_held": days_held,
            }
        )

    return result


def get_cached_embed(
    embed_type: str,
    cache_name: str = "default",
) -> list[dict[str, Any]]:
    """Fetch embed data from cache or query database.

    Each embed type is cached independently for maximum reuse.
    """
    key_functions = {
        "latest-wrs": main_wrs_cache_key,
        "latest-pbs": main_pbs_cache_key,
        "records": main_records_cache_key,
        "stats": main_stats,
    }

    query_functions: dict[str, Any] = {
        "latest-wrs": lambda: query_latest_runs(wr=True),
        "latest-pbs": lambda: query_latest_runs(wr=False),
        "records": query_records,
        "stats": query_stats,
    }

    cache = caches[cache_name]
    cache_key = key_functions[embed_type]()

    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    result = query_functions[embed_type]()
    cache.set(cache_key, result, timeout=30)  # 7 days in seconds

    return result
