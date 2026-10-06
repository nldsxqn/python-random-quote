"""Antes are dead chips in the pot before hole cards are dealt."""

from dataclasses import dataclass

from app.engine.actions import IllegalActionError


@dataclass(frozen=True)
class AnteConfig:
    mode: str
    amount: int


def parse_ante(value: object) -> AnteConfig:
    if not isinstance(value, dict):
        raise IllegalActionError("ante settings must include mode and amount")
    mode = value.get("mode")
    amount = value.get("amount")
    if mode not in {"normal", "bb_ante"}:
        raise IllegalActionError("ante mode must be normal or bb_ante")
    if isinstance(amount, bool) or not isinstance(amount, int) or amount <= 0:
        raise IllegalActionError("ante amount must be a positive integer")
    return AnteConfig(mode=mode, amount=amount)


def post_ante(game: object, config: AnteConfig) -> None:
    if config.mode == "bb_ante":
        if game.bb_seat is None:
            raise IllegalActionError("big blind seat is missing")
        game.post_dead(game.bb_seat, config.amount)
        return
    for seat in sorted(game.in_hand):
        game.post_dead(seat, config.amount)
