import calendar
from datetime import datetime, timezone

from dateutil.relativedelta import relativedelta
from django.conf import settings
from django.db.models import F, OuterRef, Q, Subquery, Sum
from srl.models import Players, RunHistory
from srl.utils import calculate_bonus

from api.v1.schemas.players import extract_gradients

# TODO: Revisit code for how RunHistory and streaks are done. I really don't want to have to redo
# the system another time, so this code will stay for now. Essentially, because I want BOTH
# current point rankings and historical, I need a bunch fo extra code to calculate what those
# older time periods would look like. Why? Because, well, Streaks take up multiple months in time;
# and, because of that, going off of my older metrics or how RunHistory holds the values means it
# is incorrect. So, this is just a bunch of spaghetti to help make it so the /ranking endpoints
# work the way they are intended.

# I am sorry.


def _obsolete_as_of(
    end_dt: datetime,
) -> Q:
    return Q(run__obsolete=False) | Q(run__obsoleted_at__gt=end_dt)


def _end_of_month_utc(year: int, month: int) -> datetime:
    last_day = calendar.monthrange(year, month)[1]
    return datetime(
        year,
        month,
        last_day,
        23,
        59,
        59,
        999999,
        tzinfo=timezone.utc,
    )


def _attach_player_fields(rows: list[dict]) -> list[dict]:
    player_ids = [r["player_id"] for r in rows]
    players = {
        p.id: p
        for p in Players.objects.filter(id__in=player_ids).select_related(
            "countrycode", "user"
        )
    }
    for row in rows:
        pid = row["player_id"]
        p = players.get(pid)

        if p and p.countrycode:
            cc = p.countrycode
            country = {
                "id": cc.id,
                "name": cc.name,
                "flag": cc.flag.url if cc.flag else None,
            }
        else:
            country = None

        row["player"] = {
            "id": pid,
            "name": p.name if p else "",
            "nickname": p.nickname if p else None,
            "url": p.url if p else "",
            "pfp": p.pfp if p else None,
            "country": country,
            "gradients": extract_gradients(p) if p else None,
        }
        del row["player_id"]

    return rows


def _assign_ranks(rows: list[dict]) -> list[dict]:
    for idx, row in enumerate(rows, start=1):
        row["rank"] = idx
    return rows


def _max_points_for(runtype: str, is_ce: bool) -> int:
    if is_ce:
        return settings.POINTS_MAX_CE
    if runtype == "main":
        return settings.POINTS_MAX_FG
    return settings.POINTS_MAX_IL


def _streak_bonus_correction(
    qs,
    end_dt: datetime,
) -> dict[str, dict[str, int]]:
    """Corrects each player's points, accounting for streak bonuses happening mid-streak."""
    candidate_qs = (
        qs.filter(
            points__gte=settings.POINTS_MAX_CE,
            run__place=1,
        )
        .select_related(
            "run__game",
        )
        .prefetch_related(
            "run__run_players",
        )
    )

    corrections: dict[str, dict[str, int]] = {}
    for entry in candidate_qs:
        run = entry.run
        is_ce = run.game.is_ce
        if is_ce:
            continue  # CE games do not earn streak bonuses lol

        max_points = _max_points_for(run.runtype, is_ce)
        if entry.points < max_points:
            continue

        cap_dt = end_dt
        if entry.end_date is not None and entry.end_date < end_dt:
            cap_dt = entry.end_date

        if entry.streak_start_date is not None:
            anchor = entry.streak_start_date
            anchor_delta = relativedelta(cap_dt, anchor)
            anchor_months = anchor_delta.years * 12 + anchor_delta.months
            total_months = min(
                max(0, anchor_months),
                settings.STREAK_MAX_MONTHS,
            )
            inherited_bonus = max(0, entry.points - max_points)
        else:
            inherited_bonus = max(0, entry.points - max_points)
            per_month = (
                settings.STREAK_BONUS_FG
                if run.runtype == "main"
                else settings.STREAK_BONUS_IL
            )
            inherited_months = (
                round(inherited_bonus / per_month) if per_month > 0 else 0
            )
            delta = relativedelta(cap_dt, entry.start_date)
            own_held_months = delta.years * 12 + delta.months
            total_months = min(
                int(inherited_months + own_held_months),
                settings.STREAK_MAX_MONTHS,
            )

        target_bonus = calculate_bonus(run.runtype, total_months, is_ce)
        delta_bonus = target_bonus - inherited_bonus
        if delta_bonus == 0:
            continue

        for rp in run.run_players.all():
            pid = rp.player_id
            if pid not in corrections:
                corrections[pid] = {"fg": 0, "il": 0}
            if run.runtype == "main":
                corrections[pid]["fg"] += delta_bonus
            elif run.runtype == "il":
                corrections[pid]["il"] += delta_bonus

    return corrections


def _start_of_month_utc(
    year: int,
    month: int,
) -> datetime:
    return datetime(year, month, 1, 0, 0, 0, tzinfo=timezone.utc)


def _start_of_next_month_utc(
    year: int,
    month: int,
) -> datetime:
    if month == 12:
        return datetime(year + 1, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
    return datetime(year, month + 1, 1, 0, 0, 0, tzinfo=timezone.utc)


def _first_entry_aggregation(
    start_dt: datetime,
    end_dt_excl: datetime,
    game_id: str | None,
) -> list[dict]:
    first_start_subq = (
        RunHistory.objects.filter(
            run=OuterRef("run"),
        )
        .order_by("start_date")
        .values("start_date")[:1]
    )

    qs = RunHistory.objects.annotate(
        first_start=Subquery(first_start_subq),
    ).filter(
        start_date=F("first_start"),
        start_date__gte=start_dt,
        start_date__lt=end_dt_excl,
    )
    if game_id is not None:
        qs = qs.filter(run__game_id=game_id)

    rows = list(
        qs.values(
            "run__players__id",
        )
        .annotate(
            total_points=Sum("points"),
            fg_points=Sum("points", filter=Q(run__runtype="main")),
            il_points=Sum("points", filter=Q(run__runtype="il")),
        )
        .filter(
            total_points__gt=0,
        )
        .order_by("-total_points"),
    )

    normalized = [
        {
            "player_id": row["run__players__id"],
            "total_points": row["total_points"] or 0,
            "fg_points": row["fg_points"] or 0,
            "il_points": row["il_points"] or 0,
        }
        for row in rows
        if row["run__players__id"] is not None
    ]
    return _assign_ranks(_attach_player_fields(normalized))


def cumulative_rankings(
    year: int,
    month: int,
    game_id: str | None,
) -> list[dict]:
    end_dt = _end_of_month_utc(year, month)
    streak_cap_dt = min(end_dt, datetime.now(timezone.utc))

    qs = (
        RunHistory.objects.filter(
            start_date__lte=end_dt,
            run__vid_status="verified",
        )
        .filter(
            Q(end_date__gt=end_dt) | Q(end_date__isnull=True),
        )
        .filter(_obsolete_as_of(end_dt))
    )
    if game_id is not None:
        qs = qs.filter(run__game_id=game_id)

    rows = list(
        qs.values(
            "run__players__id",
        )
        .annotate(
            total_points=Sum("points"),
            fg_points=Sum("points", filter=Q(run__runtype="main")),
            il_points=Sum("points", filter=Q(run__runtype="il")),
        )
        .order_by("-total_points"),
    )

    corrections = _streak_bonus_correction(qs, streak_cap_dt)

    normalized: list[dict] = []
    for row in rows:
        pid = row["run__players__id"]
        if pid is None:
            continue
        corr = corrections.get(pid, {"fg": 0, "il": 0})
        fg = (row["fg_points"] or 0) + corr["fg"]
        il = (row["il_points"] or 0) + corr["il"]
        total = fg + il
        if total <= 0:
            continue
        normalized.append(
            {
                "player_id": pid,
                "total_points": total,
                "fg_points": fg,
                "il_points": il,
            }
        )

    normalized.sort(key=lambda r: -r["total_points"])

    return _assign_ranks(_attach_player_fields(normalized))


def monthly_rankings(
    year: int,
    month: int,
    game_id: str | None,
) -> list[dict]:
    return _first_entry_aggregation(
        _start_of_month_utc(year, month),
        _start_of_next_month_utc(year, month),
        game_id,
    )


def yearly_rankings(
    year: int,
    month: int,
    game_id: str | None,
) -> list[dict]:
    year_start = datetime(year, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
    year_end_excl = _start_of_next_month_utc(year, month)
    return _first_entry_aggregation(year_start, year_end_excl, game_id)
