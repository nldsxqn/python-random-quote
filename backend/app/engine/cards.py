"""52-card deck primitives. No jokers."""

from dataclasses import dataclass

RANK_CHARS = "23456789TJQKA"
SUITS = "cdhs"


@dataclass(frozen=True, order=True)
class Card:
    rank: int
    suit: str

    def __post_init__(self) -> None:
        if self.rank not in range(2, 15) or self.suit not in SUITS:
            raise ValueError(f"invalid card {self.rank}{self.suit}")

    @property
    def code(self) -> str:
        return f"{RANK_CHARS[self.rank - 2]}{self.suit}"

    def __str__(self) -> str:
        return self.code


def parse_card(text: str) -> Card:
    raw = text.strip()
    if len(raw) != 2:
        raise ValueError(f"invalid card {text!r}")
    rank_char, suit = raw[0].upper(), raw[1].lower()
    if rank_char not in RANK_CHARS or suit not in SUITS:
        raise ValueError(f"invalid card {text!r}")
    return Card(rank=RANK_CHARS.index(rank_char) + 2, suit=suit)


def parse_cards(text: str) -> list[Card]:
    return [parse_card(part) for part in text.replace(",", " ").split()]


def standard_deck() -> list[Card]:
    return [Card(rank=rank, suit=suit) for rank in range(2, 15) for suit in SUITS]
