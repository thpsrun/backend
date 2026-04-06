import calendar
import math
import time
from datetime import date
from typing import TYPE_CHECKING, TypedDict

import requests
from dateutil.relativedelta import relativedelta
from django.conf import settings
from django.db.models import Count

from srl.models import RunHistory, RunVariableValues
from srl.srcom.schema.src import SrcRunsTimes

if TYPE_CHECKING:
    from srl.models.runs import Runs


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
    paginate: bool = False,
) -> dict:
    """Processes a Speedrun.com API GET request to return values from any of its endpoints.

    This function is primarily used to connect to a Speedrun.com API endpoint via GET. However,
    this can be used if the API call returns valid HTTP Request Codes for `420: Enhance Your Calm`
    and `503: Service Unavailable` *and* returns data in JSON format with the "data" key value.

    Arguments:
        url (str): The complete URL of the API endpoint (usually Speedrun.com) being connected to.
        paginate (bool): False by default. Some use cases related to pagination *OR* to disable
            using the "data" key value lookup.

    Returns:
        response (dict): Dictionary/JSON object from the requested API.
    """
    headers = {
        "User-Agent": "thps.run/4.0 (https://thps.run; automation@thps.run)",
    }
    response = requests.get(url, headers=headers, timeout=30)

    retries = 0
    while response.status_code == 420 or response.status_code == 503:
        retries += 1
        if retries >= 30:
            raise ValueError(
                f"SRC API rate limit exceeded after 30 retries ({url})"
            )
        print("[DEBUG] Rate limit exceeded, waiting 60 seconds...")
        time.sleep(60)
        response = requests.get(url, headers=headers, timeout=30)

    if response.status_code != 200:
        raise ValueError(
            f"SRC API request failed with status code {response.status_code}"
        )

    if paginate is False:
        response = response.json()["data"]
    else:
        response = response.json()

    return response


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
    times: SrcRunsTimes,
) -> tuple[str, str, str]:
    """Processes the returned time values of a run entry in a string.

    Arguments:
        times (SrcRunsTimes): Time data from a speedrun.

    Returns:
        tuple: A tuple containing:
            - rta (str): The written format of real-time.
            - noloads (str): The written format of loads removed time (no loads).
            - igt (str): The written format of in-game.

    Called Functions:
        - `convert_time`
    """

    rta = convert_time(times.realtime_t) if times.realtime_t > 0 else "0"
    noloads = (
        convert_time(times.realtime_noloads_t) if times.realtime_noloads_t > 0 else "0"
    )
    igt = convert_time(times.ingame_t) if times.ingame_t > 0 else "0"

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
    else:  # IL
        return int(capped * settings.STREAK_BONUS_IL)  # Cumulative floor


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
        wr_history_qs
        .select_related("run")
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
            if streak_start is None or runs_share_player(entry_player_ids, tracking_player_ids):
                streak_start = entry_start_date
            break

        if runs_share_player(entry_player_ids, tracking_player_ids):
            streak_start = entry_start_date
            tracking_player_ids = entry_player_ids
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
