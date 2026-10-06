"""Actions the engine accepts. Amounts are integer chips."""

from dataclasses import dataclass
from enum import Enum


class IllegalActionError(Exception):
    """A rejected action. Applying it must not change the hand."""


class ActionType(Enum):
    FOLD = "fold"
    CHECK = "check"
    CALL = "call"
    BET = "bet"
    RAISE = "raise"
    ALL_IN = "all_in"


@dataclass(frozen=True)
class Action:
    kind: ActionType
    amount: int | None = None

    @staticmethod
    def fold() -> "Action":
        return Action(ActionType.FOLD)

    @staticmethod
    def check() -> "Action":
        return Action(ActionType.CHECK)

    @staticmethod
    def call() -> "Action":
        return Action(ActionType.CALL)

    @staticmethod
    def bet(amount: int) -> "Action":
        """Opening bet. `amount` is the number of chips put in."""
        return Action(ActionType.BET, amount)

    @staticmethod
    def raise_to(amount: int) -> "Action":
        """Raise. `amount` is the player's total commitment on this street."""
        return Action(ActionType.RAISE, amount)

    @staticmethod
    def all_in() -> "Action":
        return Action(ActionType.ALL_IN)
