from datetime import date as date_type
from typing import Any

from django.core.cache import caches
from django.db.models import Case, F, OuterRef, Q, QuerySet, Subquery, Sum, When
from django.db.models.expressions import Expression
from django.db.models.functions import TruncDate
from srl.models import Games, Players, RunHistory, RunPlayers, Runs, RunVariableValues

from api.v1.routers.utils import (
    main_pbs_cache_key,
    main_records_cache_key,
    main_stats_cache_key,
    main_wrs_cache_key,
)
from api.v1.schemas.players import extract_gradients
from api.v1.schemas.runs import PlayerRunEmbedSchema, compute_run_subcategory


def _value_timing_subquery() -> Subquery:
    """Subquery returning the first value-level `defaulttime` for a run.

    Picks the lowest-variable-id row on the run whose linked `VariableValues`
    has a non-null `defaulttime`. This is the most-specific level in the
    precedence chain.
    """
    return Subquery(
        RunVariableValues.objects.filter(
            run=OuterRef("pk"),
            value__defaulttime__isnull=False,
        )
        .order_by("variable_id")
        .values("value__defaulttime")[:1],
    )


def _variable_timing_subquery() -> Subquery:
    """Subquery returning the first variable-level `defaulttime` for a run.

    Picks the lowest-id variable on the run that has a non-null `defaulttime`,
    matching the precedence used elsewhere in the timing resolver chain.
    """
    return Subquery(
        RunVariableValues.objects.filter(
            run=OuterRef("pk"),
            variable__defaulttime__isnull=False,
        )
        .order_by("variable_id")
        .values("variable__defaulttime")[:1],
    )


def _primary_time_secs_expr() -> Expression:
    """Build a Case expression that selects the time_secs field per run.

    Honors the full VariableValue > Variable > Category > Game precedence
    chain. Requires the queryset to be annotated with `_val_timing` via
    `_value_timing_subquery` and `_var_timing` via `_variable_timing_subquery`.
    """
    return Case(
        When(_val_timing="realtime_noloads", then=F("timenl_secs")),
        When(_val_timing="ingame", then=F("timeigt_secs")),
        When(_val_timing="realtime", then=F("time_secs")),
        When(_var_timing="realtime_noloads", then=F("timenl_secs")),
        When(_var_timing="ingame", then=F("timeigt_secs")),
        When(_var_timing="realtime", then=F("time_secs")),
        When(category__defaulttime="realtime_noloads", then=F("timenl_secs")),
        When(category__defaulttime="ingame", then=F("timeigt_secs")),
        When(category__defaulttime="realtime", then=F("time_secs")),
        When(
            runtype="il",
            game__idefaulttime="realtime_noloads",
            then=F("timenl_secs"),
        ),
        When(runtype="il", game__idefaulttime="ingame", then=F("timeigt_secs")),
        When(runtype="il", game__idefaulttime="realtime", then=F("time_secs")),
        When(game__defaulttime="realtime_noloads", then=F("timenl_secs")),
        When(game__defaulttime="ingame", then=F("timeigt_secs")),
        default=F("time_secs"),
    )


def _export_players(
    run_players: "QuerySet[RunPlayers]",
    country_detail: bool = True,
) -> list[dict[str, Any]]:
    """Export player list from a prefetched run_players queryset.

    country_detail=True  -> country as ``{id, name}`` dict.
    country_detail=False -> country as plain name string.
    """
    players: list[dict[str, Any]] = []
    for rp in run_players:
        entry: dict[str, Any] = {
            "name": rp.player.nickname if rp.player.nickname else rp.player.name,
        }
        if country_detail:
            entry["country"] = (
                {
                    "id": rp.player.countrycode.id,
                    "name": rp.player.countrycode.name,
                }
                if rp.player.countrycode
                else None
            )
        else:
            entry["country"] = (
                rp.player.countrycode.name if rp.player.countrycode else None
            )
        entry["gradients"] = extract_gradients(rp.player)
        players.append(entry)

    return (
        players
        if players
        else [{"name": "Anonymous", "country": None, "gradients": None}]
    )


def _apply_value_slug_filters(
    qs: QuerySet[Runs],
    value_slugs: list[str] | None,
) -> QuerySet[Runs]:
    """Filter queryset by variable-value slugs and apply distinct()."""
    if value_slugs:
        for slug in value_slugs:
            qs = qs.filter(runvariablevalues__value__slug=slug)
        qs = qs.distinct()
    return qs


def _build_lbs_run_dict(
    run: Runs,
) -> dict[str, Any]:
    """Build the slim run dict used across all leaderboard endpoints."""
    return {
        "id": run.id,
        "place": run.place,
        "points": run.points,
        "date": run.date.isoformat() if run.date else None,
        "video": run.video,
        "arch_video": run.arch_video,
        "url": run.url,
        "level": run.level.slug if run.level else None,
        "times": {"p_time": run.p_time},
        "players": _export_players(
            run.run_players.all(),  # type: ignore
        ),
    }


def _build_leaderboard_rows(
    rows: QuerySet,
) -> list[dict[str, Any]]:
    """Builds ranked leaderboard entries from an annotated values queryset.

    Each entry exposes a `player` identity under a nested key, matching the shape
    used in several endpoints, especially with points.

    Returns:
        list[dict[str, Any]]
    """
    result: list[dict[str, Any]] = []
    for i, row in enumerate(rows):
        g1 = row.get("player__user__gradient_1")
        g2 = row.get("player__user__gradient_2")
        g3 = row.get("player__user__gradient_3")
        gradients = (
            {
                "gradient_1": g1,
                "gradient_2": g2,
                "gradient_3": g3,
            }
            if (g1 or g2 or g3)
            else None
        )

        country_id = row.get("player__countrycode__id")
        country_name = row.get("player__countrycode__name")
        country = (
            {"id": country_id, "name": country_name, "flag": None}
            if country_id
            else None
        )

        result.append(
            {
                "rank": i + 1,
                "total_points": row["total_points"] or 0,
                "fg_points": row["fg_points"] or 0,
                "il_points": row["il_points"] or 0,
                "player": {
                    "id": row["player_id"],
                    "name": row["player__name"],
                    "nickname": row["player__nickname"],
                    "url": row["player__url"],
                    "pfp": row["player__pfp"],
                    "country": country,
                    "gradients": gradients,
                },
            }
        )
    return result


def main_player_data_export(
    run_players: "QuerySet[RunPlayers]",
) -> list[dict[str, Any]]:
    """Export player data for main page embeds (latest-wrs, latest-pbs, records)."""
    players = [
        {
            "name": rp.player.name,
            "nickname": rp.player.nickname or None,
            "country": (
                {
                    "id": rp.player.countrycode.id,
                    "name": rp.player.countrycode.name,
                }
                if rp.player.countrycode
                else None
            ),
            "gradients": extract_gradients(rp.player),
        }
        for rp in run_players
    ]

    return (
        players
        if players
        else [
            {
                "name": "Anonymous",
                "nickname": None,
                "country": None,
                "gradients": None,
            }
        ]
    )


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
            "run_players__player__user",
            "runvariablevalues_set__variable",
            "runvariablevalues_set__value",
        )
        .filter(**filters)
        .order_by("-v_date")[:5]
    )

    result = []
    for run in runs:
        result.append(
            {
                "id": run.id,
                "game_slug": run.game.slug,
                "category": {
                    "name": run.category.name if run.category else None,
                    "slug": run.category.slug if run.category else None,
                },
                "level": (
                    {
                        "name": run.level.name,
                        "slug": run.level.slug,
                    }
                    if run.level
                    else None
                ),
                "players": main_player_data_export(
                    run.run_players.all(),  # type: ignore
                ),
                "time": run.p_time,
                "date": run.v_date.isoformat() if run.v_date else None,
                "video": run.video,
                "value_slugs": [
                    rvv.value.slug
                    for rvv in run.runvariablevalues_set.all()  # type: ignore
                ],
            }
        )

    return result


def query_records() -> list[dict[str, Any]]:
    runs: list[Runs] = list(
        Runs.objects.select_related("game", "category")
        .prefetch_related(
            "run_players__player__countrycode",
            "run_players__player__user",
            "runvariablevalues_set__variable",
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
        .order_by("game__release", "category__order", "category__name")
        .annotate(o_date=TruncDate("date"))
    )

    result: list[dict[str, Any]] = []
    seen: set[tuple[str, ...]] = set()

    for run in runs:
        value_ids = tuple(
            sorted(
                rvv.value_id for rvv in run.runvariablevalues_set.all()  # type: ignore
            )
        )
        key = (
            run.game.slug,
            run.category.slug if run.category else None,
            run.time,
            value_ids,
        )
        if key in seen:
            continue
        seen.add(key)

        result.append(
            {
                "id": run.id,
                "game": {
                    "name": run.game.name,
                    "slug": run.game.slug,
                },
                "category": {
                    "name": compute_run_subcategory(run),
                    "slug": run.category.slug if run.category else None,
                },
                "players": main_player_data_export(
                    run.run_players.all(),  # type: ignore
                ),
                "time": run.p_time,
                "date": run.o_date.isoformat() if run.o_date else None,  # type: ignore
                "video": run.video,
                "value_slugs": [
                    rvv.value.slug
                    for rvv in run.runvariablevalues_set.all()  # type: ignore
                ],
            }
        )

    return result


def query_stats() -> dict[str, Any]:
    run_count = Runs.objects.only("id").all().count()
    player_count = Players.objects.only("id").all().count()

    total_time_secs = (
        Runs.objects.annotate(
            _val_timing=_value_timing_subquery(),
            _var_timing=_variable_timing_subquery(),
        ).aggregate(
            total=Sum(_primary_time_secs_expr()),
        )["total"]
        or 0.0
    )

    return {
        "runs": run_count,
        "players": player_count,
        "total_time_secs": total_time_secs,
    }


def query_player_runs(
    player_id: str,
    include_obsoletes: bool = False,
) -> list[dict[str, Any]]:
    qs: QuerySet[Runs] = (
        Runs.objects.select_related("game", "category", "level")
        .prefetch_related(
            "run_players__player__countrycode",
            "run_players__player__user",
            "runvariablevalues_set__variable",
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
        data["players"] = _export_players(
            run.run_players.all(),  # type: ignore
            country_detail=False,
        )
        result.append(data)

    return result


def query_overall_leaderboard() -> list[dict[str, Any]]:
    rows = (
        RunPlayers.objects.filter(
            run__obsolete=False,
            run__vid_status="verified",
        )
        .exclude(
            run__v_date__isnull=True,
            run__date__isnull=True,
        )
        .values(
            "player_id",
            "player__name",
            "player__nickname",
            "player__url",
            "player__pfp",
            "player__countrycode__id",
            "player__countrycode__name",
            "player__user__gradient_1",
            "player__user__gradient_2",
            "player__user__gradient_3",
        )
        .annotate(
            total_points=Sum("run__points"),
            fg_points=Sum("run__points", filter=Q(run__runtype="main")),
            il_points=Sum("run__points", filter=Q(run__runtype="il")),
        )
        .filter(total_points__gt=0)
        .order_by("-total_points")
    )

    return _build_leaderboard_rows(rows)


def query_game_leaderboard(
    game_id: str,
    game_slug: str,
) -> list[dict[str, Any]]:
    qs = RunPlayers.objects.filter(
        run__obsolete=False,
        run__vid_status="verified",
        run__game_id=game_id,
    ).exclude(
        run__v_date__isnull=True,
        run__date__isnull=True,
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
            "player__countrycode__id",
            "player__countrycode__name",
            "player__user__gradient_1",
            "player__user__gradient_2",
            "player__user__gradient_3",
        )
        .annotate(
            total_points=Sum("run__points"),
            fg_points=Sum("run__points", filter=Q(run__runtype="main")),
            il_points=Sum("run__points", filter=Q(run__runtype="il")),
        )
        .filter(total_points__gt=0)
        .order_by("-total_points")
    )

    return _build_leaderboard_rows(rows)


OLDEST_RUNS_LIMITS: dict[str, int] = {
    "thps4": 10,
    "thps12": 5,
    "thps34": 5,
}


def query_oldest_il_runs(
    game_id: str,
    game_slug: str,
) -> list[dict[str, Any]]:
    """Return the longest-held IL world records for a supported game.

    THPS4 returns the 10 oldest IL WRs (excluding `zoo-feed-the-hippos`,
    which is excluded from points calculations); THPS12 and THPS34 each
    return the 5 oldest. Full-game runs are never included. Unsupported
    slugs return an empty list.
    """
    limit = OLDEST_RUNS_LIMITS.get(game_slug)
    if limit is None:
        return []

    qs: QuerySet[Runs] = (
        Runs.objects.select_related("game", "category", "level")
        .prefetch_related(
            "run_players__player__countrycode",
            "run_players__player__user",
            "runvariablevalues_set__variable",
            "runvariablevalues_set__value",
        )
        .filter(
            game_id=game_id,
            runtype="il",
            obsolete=False,
            vid_status="verified",
            place=1,
        )
    )

    if game_slug == "thps4":
        qs = qs.exclude(level__slug="zoo-feed-the-hippos")

    runs = list(qs.order_by("date")[:limit])

    result: list[dict[str, Any]] = []
    for run in runs:
        all_rp = list(run.run_players.all())  # type: ignore
        rp = all_rp[0] if all_rp else None
        player = rp.player if rp else None

        if player and player.countrycode:
            cc = player.countrycode
            country = {
                "id": cc.id,
                "name": cc.name,
                "flag": cc.flag.url if cc.flag else None,
            }
        else:
            country = None

        days_held = (date_type.today() - run.date.date()).days if run.date else -1

        result.append(
            {
                "player": {
                    "id": player.id if player else "",
                    "name": player.name if player else "Anonymous",
                    "nickname": player.nickname if player else None,
                    "url": player.url if player else "",
                    "pfp": player.pfp if player else None,
                    "country": country,
                    "gradients": extract_gradients(player) if player else None,
                },
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
        "stats": main_stats_cache_key,
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
    cache.set(cache_key, result, timeout=30)

    return result


def query_lbs_runs(
    game_id: str,
    category_id: str,
    value_slugs: list[str] | None = None,
    level_id: str | None = None,
) -> list[dict[str, Any]]:
    """Query leaderboard runs for a specific game + category, optionally filtered by level.

    Returns slim run dicts with only frontend-required fields, built from
    prefetched relations (no N+1 queries).

    When level_id is provided, acts as an IL leaderboard query.
    Optional value_slugs filters runs to only those matching ALL given variable value slugs.
    """
    filters: dict[str, Any] = {
        "game_id": game_id,
        "category_id": category_id,
        "obsolete": False,
        "vid_status": "verified",
    }
    if level_id:
        filters["level_id"] = level_id

    qs: QuerySet[Runs] = (
        Runs.objects.filter(**filters)
        .select_related("level")
        .prefetch_related(
            "run_players__player__countrycode",
            "run_players__player__user",
            "runvariablevalues_set__variable",
            "runvariablevalues_set__value",
        )
        .order_by("place", "date")
    )

    qs = _apply_value_slug_filters(qs, value_slugs)

    return [_build_lbs_run_dict(run) for run in qs]


def query_lbs_stats(
    game_id: str,
) -> dict[str, int | float]:
    """Query game-wide run and player counts for the leaderboard stats embed."""
    base = Runs.objects.filter(
        game_id=game_id,
        vid_status="verified",
    )

    main_count = base.filter(runtype="main").count()
    il_count = base.filter(runtype="il").count()

    player_count = (
        RunPlayers.objects.filter(
            run__game_id=game_id,
            run__obsolete=False,
            run__vid_status="verified",
        )
        .values("player_id")
        .distinct()
        .count()
    )

    total_time_secs = (
        base.annotate(
            _val_timing=_value_timing_subquery(),
            _var_timing=_variable_timing_subquery(),
        ).aggregate(
            total=Sum(_primary_time_secs_expr()),
        )["total"]
        or 0.0
    )

    return {
        "main_count": main_count,
        "il_count": il_count,
        "player_count": player_count,
        "total_time_secs": total_time_secs,
    }


def query_lbs_recent(
    game_id: str,
) -> list[dict[str, Any]]:
    """Query the 5 most recently approved runs for a game."""
    runs: QuerySet[Runs] = (
        Runs.objects.filter(
            game_id=game_id,
            obsolete=False,
            vid_status="verified",
            v_date__isnull=False,
        )
        .select_related("category", "level")
        .prefetch_related(
            "run_players__player__countrycode",
            "run_players__player__user",
            "runvariablevalues_set__variable",
            "runvariablevalues_set__value",
        )
        .order_by("-v_date")[:5]
    )

    result = []
    for run in runs:
        value_slugs = [rvv.value.slug for rvv in run.runvariablevalues_set.all()]

        result.append(
            {
                "runtype": run.runtype,
                "category": run.category.id if run.category else None,
                "level": run.level.name if run.level else None,
                "subcategory": compute_run_subcategory(run),
                "p_time": run.p_time,
                "p_time_secs": run.p_time_secs,
                "place": run.place,
                "players": main_player_data_export(
                    run.run_players.all(),  # type: ignore
                ),
                "v_date": run.v_date.isoformat() if run.v_date else None,
                "video": run.video or None,
                "value_slugs": value_slugs if value_slugs else None,
            }
        )

    return result


def query_lbs_il_summary(
    game_id: str,
    value_slugs: list[str] | None = None,
) -> list[dict[str, Any]]:
    """Query IL summary grid: top 5 runs per level+category combo.

    Fetches all verified non-obsolete IL runs for a game, groups by level then category. Only
    level+category combos with actual runs are included. Optionally filters by variable value slugs.
    """
    qs: QuerySet[Runs] = (
        Runs.objects.filter(
            game_id=game_id,
            runtype="il",
            obsolete=False,
            vid_status="verified",
        )
        .select_related("category", "level")
        .prefetch_related(
            "run_players__player__countrycode",
            "run_players__player__user",
            "runvariablevalues_set__variable",
            "runvariablevalues_set__value",
        )
        .order_by("place", "date")
    )

    qs = _apply_value_slug_filters(qs, value_slugs)

    grouped: dict[tuple[str, str], list[dict[str, Any]]] = {}
    level_info: dict[str, dict[str, Any]] = {}
    category_info: dict[str, dict[str, Any]] = {}

    for run in qs:
        if not run.level or not run.category:
            continue

        level_id = run.level.id
        cat_id = run.category.id
        key = (level_id, cat_id)

        if level_id not in level_info:
            level_info[level_id] = {
                "name": run.level.name,
                "slug": run.level.slug,
                "order": run.level.order,
            }

        if cat_id not in category_info:
            category_info[cat_id] = {
                "name": run.category.name,
                "slug": run.category.slug,
                "order": run.category.order,
            }

        if key not in grouped:
            grouped[key] = []

        if len(grouped[key]) >= 5:
            continue

        grouped[key].append(_build_lbs_run_dict(run))

    levels_dict: dict[str, dict[str, Any]] = {}
    for (level_id, cat_id), runs_list in grouped.items():
        if level_id not in levels_dict:
            info = level_info[level_id]
            levels_dict[level_id] = {
                "name": info["name"],
                "slug": info["slug"],
                "order": info["order"],
                "categories": [],
            }

        cat_info = category_info[cat_id]
        levels_dict[level_id]["categories"].append(
            {
                "name": cat_info["name"],
                "slug": cat_info["slug"],
                "order": cat_info["order"],
                "runs": runs_list,
            }
        )

    for level_data in levels_dict.values():
        level_data["categories"].sort(
            key=lambda c: (c["order"] == 0, c["order"], c["name"]),
        )
        for cat in level_data["categories"]:
            del cat["order"]

    result = sorted(
        levels_dict.values(),
        key=lambda lv: (lv["order"] == 0, lv["order"], lv["name"]),
    )

    for level_data in result:
        del level_data["order"]

    return result


def query_wr_history(
    game_id: str,
    category_id: str,
    level_id: str | None = None,
    value_slugs: list[str] | None = None,
) -> dict[str, Any]:
    """Build the WR history timeline for a category/level."""

    game = Games.objects.only(
        "pointsmax",
        "ipointsmax",
    ).get(id=game_id)

    is_il = level_id is not None
    max_points = game.ipointsmax if is_il else game.pointsmax

    qs = (
        RunHistory.objects.filter(
            run__game_id=game_id,
            run__category_id=category_id,
            run__vid_status="verified",
            points__gte=max_points,
        )
        .select_related(
            "run__game",
            "run__category",
            "run__level",
        )
        .prefetch_related(
            "run__run_players__player",
            "run__run_players__player__user",
            "run__runvariablevalues_set__variable",
            "run__runvariablevalues_set__value",
        )
    )

    if level_id is not None:
        qs = qs.filter(run__level_id=level_id)
        qs = qs.filter(run__runtype="il")
    else:
        qs = qs.filter(run__runtype="main")

    if value_slugs:
        for slug in value_slugs:
            qs = qs.filter(run__runvariablevalues__value__slug=slug)
        qs = qs.distinct()

    qs = qs.order_by("start_date")

    seen_run_ids: set[str] = set()
    wr_entries: list[tuple[Any, Runs]] = []
    for entry in qs:
        if entry.run.id not in seen_run_ids:
            seen_run_ids.add(entry.run.id)
            wr_entries.append((entry, entry.run))

    results: list[dict[str, Any]] = []
    prev_time: float | None = None

    for history_entry, run in wr_entries:
        if run.p_time_secs:
            history_time = run.p_time or ""
            history_time_secs = run.p_time_secs
        else:
            history_time = run.time or ""
            history_time_secs = run.time_secs or 0.0

        delta: float | None = None
        if prev_time is not None and history_time_secs:
            delta = round(history_time_secs - prev_time, 3)

        players = []
        for rp in sorted(run.run_players.all(), key=lambda rp: rp.order):
            players.append(
                {
                    "name": rp.player.name,
                    "nickname": rp.player.nickname or None,
                    "gradients": extract_gradients(rp.player),
                }
            )
        if not players:
            players = [{"name": "Anonymous", "nickname": None, "gradients": None}]

        results.append(
            {
                "run_id": run.id,
                "players": players,
                "history_time": history_time,
                "history_time_secs": history_time_secs,
                "delta": delta,
                "video": run.video or None,
                "arch_video": run.arch_video or None,
                "start_date": history_entry.start_date.isoformat(),
                "end_date": (
                    history_entry.end_date.isoformat()
                    if history_entry.end_date
                    else None
                ),
            }
        )

        if history_time_secs:
            prev_time = history_time_secs

    subcategory: str | None = None
    if wr_entries:
        _, first_run = wr_entries[0]
        subcategory = compute_run_subcategory(first_run)

    return {
        "subcategory": subcategory,
        "entries": results,
    }
