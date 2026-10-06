"""Seat status. Disconnect and sit-out are named only; the engine never enters them."""

from dataclasses import dataclass
from enum import Enum

from app.engine.cards import Card


class PlayerStatus(Enum):
    ACTIVE = "ACTIVE"
    FOLDED = "FOLDED"
    ALL_IN = "ALL_IN"
    SITTING_OUT = "SITTING_OUT"
    DISCONNECTED = "DISCONNECTED"
    ELIMINATED = "ELIMINATED"


@dataclass
class Player:
    seat: int
    stack: int
    status: PlayerStatus = PlayerStatus.ACTIVE
    hole: tuple[Card, Card] | None = None
    committed_street: int = 0
    committed_hand: int = 0
    acted: bool = False
    can_raise: bool = True
