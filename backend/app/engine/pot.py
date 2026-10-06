"""Main pot, side pots, and the odd-chip rule."""

from collections.abc import Sequence
from dataclasses import dataclass


@dataclass(frozen=True)
class Contribution:
    seat: int
    amount: int
    folded: bool


@dataclass(frozen=True)
class Pot:
    amount: int
    eligible: tuple[int, ...]


def build_pots(contributions: Sequence[Contribution]) -> list[Pot]:
    """Layer unequal investments. Folded chips stay in the amount and cannot win."""
    invested = [item for item in contributions if item.amount > 0]
    levels = sorted({item.amount for item in invested})
    pots: list[Pot] = []
    previous = 0
    for level in levels:
        layer = [item for item in invested if item.amount >= level]
        amount = (level - previous) * len(layer)
        eligible = tuple(item.seat for item in layer if not item.folded)
        pots.append(Pot(amount=amount, eligible=eligible))
        previous = level
    return pots


def odd_chip_order(seats: Sequence[int], button: int, seat_count: int) -> list[int]:
    """Tied winners clockwise, starting with the one nearest the left of the button."""
    wanted = set(seats)
    ordered: list[int] = []
    seat = (button + 1) % seat_count
    for _ in range(seat_count):
        if seat in wanted:
            ordered.append(seat)
        seat = (seat + 1) % seat_count
    return ordered


def split_amount(amount: int, ordered_winners: Sequence[int]) -> dict[int, int]:
    count = len(ordered_winners)
    if count == 0:
        raise ValueError("cannot split a pot with no winners")
    share, remainder = divmod(amount, count)
    awards = dict.fromkeys(ordered_winners, share)
    for seat in ordered_winners[:remainder]:
        awards[seat] += 1
    return awards
