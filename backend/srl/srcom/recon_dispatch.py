from __future__ import annotations

from typing import Any

from srl.models.reconciliation import ReconPhase

_phase_tasks: dict[str, Any] = {}

PHASE_2 = ReconPhase.P2.value
PHASE_3 = ReconPhase.P3.value


def register_phase_task(
    phase: str,
    task: Any,
) -> None:
    _phase_tasks[phase] = task


def get_phase_dispatcher(
    phase: str,
) -> Any:
    """Return the Celery task registered for ``phase`` or raise ``KeyError``."""
    try:
        return _phase_tasks[phase]
    except KeyError as exc:
        raise KeyError(
            f"No phase dispatcher registered for {phase!r}; "
            f"known phases: {sorted(_phase_tasks)}",
        ) from exc


def is_phase_registered(
    phase: str,
) -> bool:
    return phase in _phase_tasks
