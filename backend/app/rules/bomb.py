"""Bomb pot. One board unless boards is 2."""

from dataclasses import dataclass

from app.engine.actions import IllegalActionError


@dataclass(frozen=True)
class BombConfig:
    amount: int
    boards: int = 1


def parse_bomb(value: object) -> BombConfig:
    if not isinstance(value, dict):
        raise IllegalActionError("bomb pot settings must include amount")
    boards = value.get("boards", 1)
    amount = value.get("amount")
    if boards not in {1, 2}:
        raise IllegalActionError("bomb pot boards must be 1 or 2")
    if isinstance(amount, bool) or not isinstance(amount, int) or amount <= 0:
        raise IllegalActionError("bomb pot amount must be a positive integer")
    return BombConfig(amount=amount, boards=boards)


def post_bomb(game: object, config: BombConfig) -> None:
    for seat in sorted(game.in_hand):
        game.post_dead(seat, config.amount)
