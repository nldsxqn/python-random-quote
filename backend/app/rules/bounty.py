"""Seven-deuce bounty. Only 72 offsuit, and only for a showdown win by default."""

from dataclasses import dataclass

from app.engine.actions import IllegalActionError
from app.engine.cards import Card


@dataclass(frozen=True)
class BountyConfig:
    payment_per_player_bb: int
    require_showdown: bool = True


def parse_bounty(value: object) -> BountyConfig:
    if not isinstance(value, dict):
        raise IllegalActionError("seven-deuce settings must include payment_per_player_bb")
    payment = value.get("payment_per_player_bb")
    require = value.get("require_showdown", True)
    if isinstance(payment, bool) or not isinstance(payment, int) or payment <= 0:
        raise IllegalActionError("payment_per_player_bb must be a positive integer")
    if not isinstance(require, bool):
        raise IllegalActionError("require_showdown must be true or false")
    return BountyConfig(payment_per_player_bb=payment, require_showdown=require)


def is_seven_deuce_offsuit(hole: tuple[Card, Card] | None) -> bool:
    if hole is None or len(hole) != 2:
        return False
    left, right = hole
    return {left.rank, right.rank} == {2, 7} and left.suit != right.suit


def apply_bounty(game: object, config: BountyConfig, winners: set[int]) -> None:
    if config.require_showdown and not game.showdown_seats:
        return
    heroes = [
        seat
        for seat in sorted(winners)
        if is_seven_deuce_offsuit(game.players[seat].hole)
    ]
    if not heroes:
        return
    payment = config.payment_per_player_bb * game.big_blind
    payments: list[dict] = []
    total = 0
    for hero in heroes:
        for seat in sorted(game.in_hand):
            if seat == hero or seat in heroes:
                continue
            player = game.players[seat]
            paid = min(payment, player.stack)
            partial = paid < payment
            player.stack -= paid
            game.players[hero].stack += paid
            total += paid
            payments.append(
                {
                    "seat": seat,
                    "winner": hero,
                    "amount": paid,
                    "partial": partial,
                }
            )
    game.bounty += total
    game.bounty_payments.extend(payments)
