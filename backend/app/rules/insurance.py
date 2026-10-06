"""Simplified all-in insurance before the river. The price comes from equity.

Accepting locks the favorite's share of the pot. Declining runs the river.
The label is always simplified. Chips only move out of the existing pot.
"""

from app.engine.cards import standard_deck
from app.engine.evaluator import evaluate
from app.engine.short_deck import evaluate_short, short_deck


def quote(game: object) -> dict | None:
    alive = game._alive_seats()
    if len(alive) < 2:
        return None
    board = list(game.board)
    if len(board) != 4:
        return None
    dead = set(board)
    for seat in alive:
        hole = game.players[seat].hole
        if hole is None:
            return None
        dead.update(hole)
    deck = short_deck() if game.variant == "short_deck" else standard_deck()
    remaining = [card for card in deck if card not in dead]
    if not remaining:
        return None
    rank = evaluate_short if game.variant == "short_deck" else evaluate
    equities = {seat: 0.0 for seat in alive}
    for river in remaining:
        ranks = {seat: rank(game.players[seat].hole, [*board, river]) for seat in alive}
        best = max(ranks.values())
        tied = [seat for seat in alive if ranks[seat] == best]
        for seat in tied:
            equities[seat] += 1 / len(tied)
    for seat in equities:
        equities[seat] /= len(remaining)
    hero = max(alive, key=lambda seat: (equities[seat], -seat))
    pot = sum(player.committed_hand for player in game.players)
    if pot <= 0:
        return None
    payout = int(round(equities[hero] * pot))
    payout = min(pot, max(0, payout))
    return {
        "label": "simplified",
        "seat": hero,
        "equity": equities[hero],
        "premium": pot - payout,
        "payout": payout,
    }
