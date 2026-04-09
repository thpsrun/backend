from srl.models import RunVariableValues
from srl.models.runs import Runs


def resolve_leaderboard(
    run: Runs,
) -> dict:
    """Build the unique leaderboard signature for a run.

    A "leaderboard variant" is a unique combination of game, category, level,
    run type, and variable values that identifies one distinct leaderboard.
    Used by the recalculation system to know which leaderboard to reprocess.
    """
    rvvs = RunVariableValues.objects.filter(
        run=run,
    ).values_list("variable_id", "value_id")

    return {
        "game_id": run.game.id,
        "category_id": run.category.id,
        "level_id": run.level.id if run.level else None,
        "runtype": run.runtype,
        "variable_value_map": dict(rvvs),
    }
