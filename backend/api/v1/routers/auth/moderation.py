from typing import TYPE_CHECKING

from srl.models.src_sync import SRCSyncTask

from api.v1.schemas.runs import ModeratorActionIn

if TYPE_CHECKING:
    from srl.models.players import Players
    from srl.models.runs import Runs


class ModerationError(Exception):
    """Raised when a moderator action cannot be applied.

    Carries an HTTP-style status code so the calling endpoint can map it
    straight onto an ErrorResponse without inspecting the message.
    The surrounding transaction.atomic() block rolls back on raise.
    """

    def __init__(
        self,
        code: int,
        message: str,
    ) -> None:
        self.code = code
        self.message = message
        super().__init__(message)


def _has_src_key(
    player: "Players",
) -> bool:
    if not player.user:
        return False
    return player.user.encrypted_api_key is not None


def _apply_moderation(
    run: "Runs",
    action_in: ModeratorActionIn,
    *,
    actor_player: "Players",
) -> SRCSyncTask | None:
    """Apply a moderator verdict to a run."""
    action = action_in.action

    if action in ("verify", "reject"):
        if run.vid_status != "new":
            raise ModerationError(
                400,
                f"Run is already {run.vid_status}.",
            )
        if not _has_src_key(actor_player):
            raise ModerationError(
                403,
                "No SRC API key stored. Add one at /auth/me/src-key.",
            )
        if action == "reject" and not action_in.reason:
            raise ModerationError(
                400,
                "A reason is required when rejecting a run.",
            )

        new_status = "verified" if action == "verify" else "rejected"
        run.vid_status = new_status
        run.approver = actor_player

        src_payload: dict = {"status": {"status": new_status}}
        if action == "reject" and action_in.reason:
            src_payload["status"]["reason"] = action_in.reason

        sync_task = SRCSyncTask.objects.create(
            run=run,
            action=(
                SRCSyncTask.ActionType.VERIFY
                if action == "verify"
                else SRCSyncTask.ActionType.REJECT
            ),
            payload=src_payload,
            moderator=actor_player,
        )
        return sync_task

    if action == "review":
        if run.vid_status not in ("new", "review"):
            raise ModerationError(
                409,
                f"Run is currently {run.vid_status}; only 'new' or "
                "'review' runs can be sent for review.",
            )
        if not action_in.notes or not action_in.notes.strip():
            raise ModerationError(
                400,
                "Notes are required when sending a run back for review.",
            )

        # This is to mainly ensure you cannot send back a run to a player with no thps.run account.
        has_claimed_runner = run.players.filter(
            user__isnull=False,
            claim_status="claimed",
        ).exists()
        if not has_claimed_runner:
            raise ModerationError(
                409,
                "Run has no claimed thps.run player who could resubmit; "
                "reject the run instead.",
            )
        run.vid_status = "review"
        run.review_notes = action_in.notes
        return None

    raise ModerationError(
        400,
        f"Unknown moderator action: {action}.",
    )
