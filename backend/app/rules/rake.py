"""Rake taken from the pot at payout. It is not part of the pot the winner is shown."""

from dataclasses import dataclass

from app.engine.actions import IllegalActionError
from app.engine.pot import Pot


@dataclass(frozen=True)
class RakeConfig:
    percentage: int
    cap: int
    no_flop_no_drop: bool = True


def parse_rake(value: object) -> RakeConfig:
    if not isinstance(value, dict):
        raise IllegalActionError("rake settings must include percentage, cap, and no_flop_no_drop")
    percentage = value.get("percentage")
    cap = value.get("cap")
    no_flop = value.get("no_flop_no_drop", True)
    bad_percent = isinstance(percentage, bool) or not isinstance(percentage, int)
    if bad_percent or not 0 <= percentage <= 100:
        raise IllegalActionError("rake percentage must be an integer from 0 to 100")
    if isinstance(cap, bool) or not isinstance(cap, int) or cap < 0:
        raise IllegalActionError("rake cap must be a non-negative integer")
    if not isinstance(no_flop, bool):
        raise IllegalActionError("no_flop_no_drop must be true or false")
    return RakeConfig(percentage=percentage, cap=cap, no_flop_no_drop=no_flop)


def apply_rake(game: object, config: RakeConfig, pots: list[Pot]) -> list[Pot]:
    if config.no_flop_no_drop and len(game.board) < 3:
        game.rake = 0
        return pots
    total = sum(pot.amount for pot in pots)
    rake = min(config.cap, (total * config.percentage) // 100)
    game.rake = rake
    left = rake
    updated: list[Pot] = []
    for pot in pots:
        take = min(pot.amount, left)
        left -= take
        updated.append(Pot(amount=pot.amount - take, eligible=pot.eligible))
    return updated
