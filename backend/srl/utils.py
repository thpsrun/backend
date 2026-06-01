import calendar
import logging
import math
import time
from datetime import date
from typing import TYPE_CHECKING, Iterator, TypedDict

import requests
from dateutil.relativedelta import relativedelta
from django.conf import settings
from django.db.models import Count

from srl.models import RunHistory, RunVariableValues
from srl.srcom.schema.src import SrcRunsTimes

if TYPE_CHECKING:
    from srl.models.runs import Runs

logger = logging.getLogger(__name__)

SRC_HEADERS = {
    "User-Agent": "thps.run/4.0 (https://thps.run; automation@thps.run)",
}
SRC_MAX_RETRIES = 10
SRC_BACKOFF_SECS = 60


def convert_time(
    secs: float,
) -> str:
    """Converts the time given into a string.

    Arguments:
        secs (float): The seconds of a speedrun time.

    Returns:
        final_time (str): The processed string format for a speedrun.
    """
    hours, remainder = divmod(secs, 3600)
    minutes, seconds = divmod(remainder, 60)
    seconds, milliseconds = divmod(round(seconds, 3) * 1000, 1000)
    milliseconds = str(int(milliseconds)).zfill(3)

    if hours >= 1:
        final_time = f"{int(hours)}h "
    else:
        final_time = ""

    final_time += f"{int(minutes)}m "

    if seconds < 10:
        final_time += f"0{int(seconds)}s "
    else:
        final_time += f"{int(seconds)}s "

    if milliseconds != "000":
        final_time += f"{milliseconds}ms"
    else:
        final_time = final_time.rstrip(" ")

    return final_time


def src_api(
    url: str,
    raw: bool = False,
) -> dict | list:
    """Processes a Speedrun.com API v1 GET request to return values from any of its endpoints.

    Retries on 420 (Enhance Your Calm) and 503 (Service Unavailable) up to SRC_MAX_RETRIES
    times with a fixed SRC_BACKOFF_SECS sleep between attempts.

    Arguments:
        url (str): The complete URL of the API endpoint being called.
        raw (bool): If True, return the full JSON envelope (e.g., when pagination links or
            sibling fields are needed). Default unwraps and returns the "data" field.

    Returns:
        dict | list: The "data" field (dict or list depending on the endpoint), or the
            full envelope when raw=True.
    """
    response = None
    for attempt in range(1, SRC_MAX_RETRIES + 1):
        response = requests.get(url, headers=SRC_HEADERS, timeout=30)
        if response.status_code not in (420, 503):
            break

        logger.warning(
            "SRC rate limit (%s) on attempt %d/%d, sleeping %ds: %s",
            response.status_code,
            attempt,
            SRC_MAX_RETRIES,
            SRC_BACKOFF_SECS,
            url,
        )
        time.sleep(SRC_BACKOFF_SECS)
    else:
        raise ValueError(
            f"SRC API rate limit exceeded after {SRC_MAX_RETRIES} retries ({url})"
        )

    if response.status_code != 200:
        raise ValueError(
            f"SRC API request failed with status code {response.status_code}"
        )

    payload = response.json()
    return payload if raw else payload["data"]


def src_api_paginate(
    base_url: str,
    page_size: int = 200,
) -> Iterator[dict]:
    """Helper function for more SRC API pagination stuff."""
    sep = "&" if "?" in base_url else "?"
    url: str | None = f"{base_url}{sep}max={page_size}"
    while url:
        payload = src_api(url, raw=True)
        assert isinstance(payload, dict)
        for row in payload.get("data") or []:
            yield row

        url = None
        for link in (payload.get("pagination") or {}).get("links") or []:
            if link.get("rel") == "next":
                url = link.get("uri")
                break


def points_formula(
    wr: float,
    run: float,
    max_points: int,
    short: bool = False,
) -> int:
    """Processes points based on an algorithmic formula.

    Arguments:
        wr (float): The world record time (as a float).
        run (float): The personal best time (as a float).
        max_points (int): Maximum points of a speedrun
        short (bool): If True, a more scaled formula is applied (usually for shorter speedruns).

    Returns:
        int: Points awarded to the speedrun in comparison to world record.
    """
    log = 4.8284
    if short:
        log = log * math.sqrt(wr / 60)

    return math.floor(math.pow(math.e, log * ((wr / run) - 1)) * max_points)


class TimeDict(TypedDict):
    realtime_t: int
    realtime_noloads_t: int
    ingame_t: int


def time_conversion(
    times: SrcRunsTimes | dict,
) -> tuple[str, str, str]:
    """Processes the returned time values of a run entry in a string.

    Arguments:
        times (SrcRunsTimes | dict): Time data from a speedrun. Accepts either
            the Pydantic model or a dict (e.g., the result of `model_dump()`).

    Returns:
        tuple: A tuple containing:
            - rta (str): The written format of real-time.
            - noloads (str): The written format of loads removed time (no loads).
            - igt (str): The written format of in-game.
    """

    if isinstance(times, dict):
        rta_t = times.get("realtime_t") or 0
        nl_t = times.get("realtime_noloads_t") or 0
        igt_t = times.get("ingame_t") or 0
    else:
        rta_t = times.realtime_t or 0
        nl_t = times.realtime_noloads_t or 0
        igt_t = times.ingame_t or 0

    rta = convert_time(rta_t) if rta_t > 0 else "0"
    noloads = convert_time(nl_t) if nl_t > 0 else "0"
    igt = convert_time(igt_t) if igt_t > 0 else "0"

    return rta, noloads, igt


def calculate_bonus(
    runtype: str,
    streak_months: int,
    is_ce: bool,
) -> int:
    """Calculate streak bonus points using cumulative rounding.

    Arguments:
        runtype (str): The run type ("main" for full-game, "il" for individual level).
        streak_months (int): Number of full months the WR has been held (0-4).
        is_ce (bool): True if the game is a category extension (no streak bonus).

    Returns:
        int: The streak bonus points to add to the base WR points.
    """
    if is_ce or streak_months <= 0:
        return 0

    capped = min(streak_months, settings.STREAK_MAX_MONTHS)

    if runtype == "main":
        return int(capped * settings.STREAK_BONUS_FG)
    else:
        return int(capped * settings.STREAK_BONUS_IL)


def runs_share_player(
    player_ids_a: set[str],
    player_ids_b: set[str],
) -> bool:
    """Check if two runs share at least one player.

    Arguments:
        player_ids_a (set[str]): Set of player IDs from the first run.
        player_ids_b (set[str]): Set of player IDs from the second run.

    Returns:
        bool: True if the runs share at least one player.
    """
    return bool(player_ids_a & player_ids_b)


def get_streak_start_date(
    run: "Runs",
) -> date | None:
    """Trace back through RunHistory to find when this player's WR streak began.

    If a runner breaks their own record, the streak continues. If any other player beats them, then
    the streak ends. The script will early exit after tracing up to 4 months (max of the streak).


    Arguments:
        run (Runs): The current WR run to trace the streak for.

    Returns:
        date | None: The date when the continuous WR streak began, or None if not a WR.
    """

    current_player_ids = {p.id for p in run.players.all()}
    if not current_player_ids:
        return None

    game = run.game
    if game.is_ce:
        max_points = settings.POINTS_MAX_CE
    elif run.runtype == "main":
        max_points = game.pointsmax
    else:
        max_points = game.ipointsmax

    wr_history_qs = RunHistory.objects.filter(
        run__game=run.game,
        run__category=run.category,
        run__level=run.level,
        run__runtype=run.runtype,
        points__gte=max_points,
    )

    rvvs = list(RunVariableValues.objects.filter(run=run))
    if rvvs:
        for rvv in rvvs:
            wr_history_qs = wr_history_qs.filter(
                run__runvariablevalues__variable=rvv.variable,
                run__runvariablevalues__value=rvv.value,
            )
    else:
        wr_history_qs = wr_history_qs.annotate(
            rv_count=Count("run__runvariablevalues", distinct=True)
        ).filter(rv_count=0)

    wr_history = (
        wr_history_qs.select_related("run")
        .prefetch_related("run__players")
        .order_by("-start_date")
    )

    if not wr_history.exists():
        return None

    cutoff_date = date.today() - relativedelta(months=settings.STREAK_MAX_MONTHS)

    streak_start: date | None = None
    tracking_player_ids = current_player_ids.copy()

    for entry in wr_history:
        entry_player_ids = {p.id for p in entry.run.players.all()}
        entry_start_date = entry.start_date.date()

        if entry_start_date < cutoff_date:
            if streak_start is None or runs_share_player(
                entry_player_ids, tracking_player_ids
            ):
                streak_start = entry_start_date
            break

        if runs_share_player(entry_player_ids, tracking_player_ids):
            streak_start = entry_start_date
            tracking_player_ids = entry_player_ids
        elif entry.end_date is None:
            continue
        else:
            break

    return streak_start


def get_anniversary(
    original_day: int,
    target_year: int,
    target_month: int,
) -> int:
    """Get the appropriate anniversary day for a given month.

    This function will get the anniversary day of the previous month, while also dealing with
    edge cases where the next month doesn't have the day in question (e.g. January 31 ->
    February 28).

    Arguments:
        original_day (int): The day of month when the streak started.
        target_year (int): The year of the target anniversary.
        target_month (int): The month of the target anniversary.

    Returns:
        int: The day to use for the anniversary in the target month.
    """

    days_in_month = calendar.monthrange(target_year, target_month)[1]
    return min(original_day, days_in_month)
