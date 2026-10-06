"""Deck providers. Production shuffles with secrets.SystemRandom."""

import random
import secrets
from collections.abc import Sequence
from typing import Protocol

from app.engine.cards import Card


class DeckProvider(Protocol):
    def shuffle(self, cards: Sequence[Card]) -> list[Card]:
        """Return a permutation of `cards`. Index 0 is drawn first."""


class SystemRandomDeck:
    def shuffle(self, cards: Sequence[Card]) -> list[Card]:
        deck = list(cards)
        secrets.SystemRandom().shuffle(deck)
        return deck


class SeededDeck:
    def __init__(self, seed: int) -> None:
        self.seed = seed

    def shuffle(self, cards: Sequence[Card]) -> list[Card]:
        deck = list(cards)
        random.Random(self.seed).shuffle(deck)
        return deck


class RiggedDeck:
    """Draw `order` first. Any omitted cards follow in the given deck order."""

    def __init__(self, order: Sequence[Card]) -> None:
        self.order = list(order)

    def shuffle(self, cards: Sequence[Card]) -> list[Card]:
        remaining = list(cards)
        drawn: list[Card] = []
        for card in self.order:
            try:
                remaining.remove(card)
            except ValueError as exc:
                raise ValueError(f"rigged card {card} is missing or duplicated") from exc
            drawn.append(card)
        drawn.extend(remaining)
        return drawn
