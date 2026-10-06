"""Short deck (6+). This is not hold'em. `evaluate` is unchanged.

Ranks are six through ace. A-6-7-8-9 is a straight. A flush beats a full house.
"""

from collections import Counter
from collections.abc import Sequence
from itertools import combinations

from app.engine.cards import SUITS, Card
from app.engine.evaluator import HandStrength

_CATEGORIES = (
    "high card",
    "pair",
    "two pair",
    "three of a kind",
    "straight",
    "full house",
    "flush",
    "four of a kind",
    "straight flush",
)


def short_deck() -> list[Card]:
    return [Card(rank=rank, suit=suit) for rank in range(6, 15) for suit in SUITS]


def evaluate_short(hole: Sequence[Card], board: Sequence[Card]) -> HandStrength:
    cards = [*hole, *board]
    if len(cards) < 5:
        raise ValueError("evaluation needs at least 5 cards")
    if any(card.rank < 6 for card in cards):
        raise ValueError("short deck cards start at six")
    best = max(_five(combo) for combo in combinations(cards, 5))
    return best


def _five(cards: tuple[Card, ...]) -> HandStrength:
    ranks = sorted((card.rank for card in cards), reverse=True)
    flush = len({card.suit for card in cards}) == 1
    straight, top = _straight(ranks)
    counts = Counter(ranks)
    pattern = tuple(sorted(counts.values(), reverse=True))
    ordered = sorted(counts, key=lambda rank: (counts[rank], rank), reverse=True)
    if straight and flush:
        return _strength(8, [top])
    if pattern == (4, 1):
        return _strength(7, ordered)
    if flush:
        return _strength(6, ranks)
    if pattern == (3, 2):
        return _strength(5, ordered)
    if straight:
        return _strength(4, [top])
    if pattern == (3, 1, 1):
        return _strength(3, ordered)
    if pattern == (2, 2, 1):
        return _strength(2, ordered)
    if pattern == (2, 1, 1, 1):
        return _strength(1, ordered)
    return _strength(0, ranks)


def _straight(ranks: list[int]) -> tuple[bool, int]:
    unique = sorted(set(ranks))
    if unique == [6, 7, 8, 9, 14]:
        return True, 9
    if len(unique) == 5 and unique[-1] - unique[0] == 4:
        return True, unique[-1]
    return False, 0


def _strength(category: int, kickers: list[int]) -> HandStrength:
    slots = [*kickers, 0, 0, 0, 0, 0][:5]
    value = category
    for rank in slots:
        value = value * 15 + rank
    return HandStrength(index=value, category=_CATEGORIES[category])
