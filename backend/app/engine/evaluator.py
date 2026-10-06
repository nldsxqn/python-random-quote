"""Best five-card high hand. PokerKit ranks the cards; it does not run the game."""

from collections.abc import Sequence
from dataclasses import dataclass
from enum import Enum

from pokerkit import StandardHighHand

from app.engine.cards import Card


@dataclass(frozen=True)
class HandStrength:
    """Higher `index` wins. Equal indexes tie. Suits are not part of the rank."""

    index: int
    category: str

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, HandStrength):
            return NotImplemented
        return self.index == other.index

    def __lt__(self, other: object) -> bool:
        if not isinstance(other, HandStrength):
            return NotImplemented
        return self.index < other.index

    def __hash__(self) -> int:
        return hash(self.index)


def evaluate(hole: Sequence[Card], board: Sequence[Card]) -> HandStrength:
    cards = [*hole, *board]
    if len(cards) < 5:
        raise ValueError("evaluation needs at least 5 cards")
    hand = StandardHighHand.from_game("".join(card.code for card in cards))
    label = hand.entry.label
    category = label.value if isinstance(label, Enum) else str(label)
    return HandStrength(index=hand.entry.index, category=category)
