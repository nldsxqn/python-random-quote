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
    cards: tuple[str, ...] = ()

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
    return HandStrength(
        index=hand.entry.index,
        category=category,
        cards=tuple(_pokerkit_code(card) for card in hand.cards),
    )


def canonical_category(label: str) -> str:
    """Stable English name for a made hand. The client only translates it."""
    key = label.strip().lower()
    return _CANONICAL.get(key, label)


def _pokerkit_code(card: object) -> str:
    rank = getattr(card, "rank")
    suit = getattr(card, "suit")
    rank_text = getattr(rank, "value", rank)
    suit_text = getattr(suit, "value", suit)
    return f"{rank_text}{suit_text}"


_CANONICAL = {
    "high card": "High card",
    "one pair": "One pair",
    "pair": "One pair",
    "two pair": "Two pair",
    "three of a kind": "Three of a kind",
    "straight": "Straight",
    "flush": "Flush",
    "full house": "Full house",
    "four of a kind": "Four of a kind",
    "straight flush": "Straight flush",
}
