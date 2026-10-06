"""UTG, Mississippi, and a chosen-seat straddle. The straddler acts last preflop."""

from dataclasses import dataclass

from app.engine.actions import IllegalActionError


@dataclass(frozen=True)
class StraddleConfig:
    amount_bb: int
    style: str
    seat: int | None = None


def parse_straddle(value: object) -> StraddleConfig:
    if not isinstance(value, dict):
        raise IllegalActionError("straddle settings must include style and amount_bb")
    style = str(value.get("style", "")).strip().lower()
    if style not in {"utg", "mississippi", "custom"}:
        raise IllegalActionError("straddle style must be utg, mississippi, or custom")
    amount_bb = value.get("amount_bb")
    if isinstance(amount_bb, bool) or not isinstance(amount_bb, int) or amount_bb < 2:
        raise IllegalActionError("straddle amount_bb must be an integer of at least 2")
    seat = value.get("seat")
    if style == "custom":
        if isinstance(seat, bool) or not isinstance(seat, int) or seat < 0:
            raise IllegalActionError("custom straddle needs a seat")
    elif seat is not None:
        raise IllegalActionError("only a custom straddle takes a seat")
    return StraddleConfig(amount_bb=amount_bb, style=style, seat=seat)


def post_straddle(game: object, config: StraddleConfig) -> None:
    if config.style == "utg":
        if game.bb_seat is None:
            raise IllegalActionError("big blind seat is missing")
        seat = game._next_in_hand(game.bb_seat)
    elif config.style == "mississippi":
        seat = game.button
    else:
        seat = config.seat
        if seat not in game.in_hand:
            raise IllegalActionError("custom straddle seat is not in the hand")
    player = game.players[seat]
    target = config.amount_bb * game.big_blind
    already = player.committed_street
    need = target - already
    if need > 0:
        game._take(seat, need)
    game.straddle_seat = seat
    posted = player.committed_street - already
    if posted >= game.big_blind and player.committed_street >= target:
        game.min_raise_increment = player.committed_street - game.big_blind
    else:
        game.min_raise_increment = game.big_blind
