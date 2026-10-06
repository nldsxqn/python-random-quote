"""Public snapshot. Other players' hole cards stay hidden unless they showed down."""

from dataclasses import dataclass
from enum import Enum

from app.engine.cards import Card
from app.engine.player import PlayerStatus
from app.engine.pot import Pot


class Street(Enum):
    WAITING = "WAITING"
    POSTING_BLINDS = "POSTING_BLINDS"
    PREFLOP = "PREFLOP"
    FLOP = "FLOP"
    TURN = "TURN"
    RIVER = "RIVER"
    SHOWDOWN = "SHOWDOWN"
    PAYOUT = "PAYOUT"
    HAND_COMPLETE = "HAND_COMPLETE"


@dataclass(frozen=True)
class PublicPlayer:
    seat: int
    stack: int
    status: PlayerStatus
    committed_street: int
    committed_hand: int
    hole_cards: tuple[Card, Card] | None


@dataclass(frozen=True)
class PublicView:
    street: Street
    button: int
    small_blind_seat: int | None
    big_blind_seat: int | None
    actor: int | None
    board: tuple[Card, ...]
    pot: int
    pots: tuple[Pot, ...]
    players: tuple[PublicPlayer, ...]
