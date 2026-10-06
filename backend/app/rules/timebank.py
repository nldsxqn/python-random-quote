"""Server-owned decision clock. Facing a bet, timeout folds. Otherwise it checks."""

from dataclasses import dataclass

from app.engine.actions import Action, IllegalActionError


@dataclass(frozen=True)
class TimeBankConfig:
    seconds: int


def parse_time_bank(value: object) -> TimeBankConfig:
    if not isinstance(value, dict):
        raise IllegalActionError("time bank settings must include seconds")
    seconds = value.get("seconds")
    if isinstance(seconds, bool) or not isinstance(seconds, int) or seconds <= 0:
        raise IllegalActionError("time bank seconds must be a positive integer")
    return TimeBankConfig(seconds=seconds)


def timeout_action(game: object) -> Action:
    if game.actor is None:
        raise IllegalActionError("no action is pending")
    player = game.players[game.actor]
    to_call = game.current_bet - player.committed_street
    if to_call > 0:
        return Action.fold()
    return Action.check()


def remaining_seconds(deadline: float | None, now: float) -> int | None:
    if deadline is None:
        return None
    return max(0, int(deadline - now))
