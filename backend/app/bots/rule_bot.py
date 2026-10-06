"""Thresholds, position, and pot odds, with a seeded random mix. It only plays legally."""

import random

from app.bots.base import BotAction, PokerBot, legal_kinds, safe_action, sized

_RANK = "23456789TJQKA"
_LATE = {"BTN": 0.12, "CO": 0.08, "HJ": 0.04, "BB": 0.05}
_EARLY = {"UTG": -0.08, "UTG1": -0.06, "MP": -0.02}


class RuleBot(PokerBot):
    def __init__(self, seed: int = 0, mix: float = 0.08) -> None:
        self.rng = random.Random(seed)
        self.mix = mix

    def decide(self, observation: dict) -> BotAction:
        legal = legal_kinds(observation)
        if not legal:
            return safe_action(observation)
        if self.rng.random() < self.mix:
            kind = self.rng.choice(legal)
            return sized(observation, kind)
        return self._by_threshold(observation, legal)

    def _by_threshold(self, observation: dict, legal: list[str]) -> BotAction:
        game = observation.get("game", {})
        score = _strength(observation) + _position_adjust(observation)
        to_call = _int(game.get("to_call"))
        pot = _int(game.get("pot"))
        odds = to_call / (pot + to_call) if to_call > 0 else 0.0
        if to_call <= 0:
            if score >= 0.62 and "bet" in legal:
                return sized(observation, "bet")
            if "check" in legal:
                return BotAction("check")
            return sized(observation, legal[0])
        if score >= 0.8 and score >= odds + 0.08 and "raise" in legal:
            return sized(observation, "raise")
        if score >= odds and "call" in legal:
            return BotAction("call")
        if "fold" in legal:
            return BotAction("fold")
        return safe_action(observation)


def _strength(observation: dict) -> float:
    holes = observation.get("you", {}).get("hole_cards") or []
    board = observation.get("game", {}).get("board") or []
    if len(holes) != 2:
        return 0.0
    if len(board) < 3:
        return _preflop(holes)
    return _made(holes, board)


def _preflop(holes: list[str]) -> float:
    hi, lo = sorted((_rank(card) for card in holes), reverse=True)
    suited = holes[0][1] == holes[1][1]
    if hi == lo:
        return 0.45 + hi / 40
    if hi >= 13 and lo >= 12:
        return 0.7 if suited else 0.62
    if hi >= 12 and lo >= 10:
        return 0.55 if suited else 0.48
    if suited and hi - lo <= 2 and lo >= 6:
        return 0.42
    return 0.22


def _made(holes: list[str], board: list[str]) -> float:
    cards = [*holes, *board]
    ranks = [_rank(card) for card in cards]
    suits = [card[1] for card in cards]
    counts: dict[int, int] = {}
    for rank in ranks:
        counts[rank] = counts.get(rank, 0) + 1
    groups = sorted(counts.values(), reverse=True)
    flush = max(suits.count(suit) for suit in suits) >= 5
    straight = _straight(set(ranks))
    if flush and straight:
        return 0.98
    if groups[0] >= 4:
        return 0.95
    if groups[0] >= 3 and len(groups) > 1 and groups[1] >= 2:
        return 0.9
    if flush:
        return 0.84
    if straight:
        return 0.8
    if groups[0] >= 3:
        return 0.72
    if groups[0] >= 2 and len(groups) > 1 and groups[1] >= 2:
        return 0.64
    hole_ranks = {_rank(card) for card in holes}
    if groups[0] >= 2 and hole_ranks & set(counts):
        return 0.5
    return 0.28


def _straight(ranks: set[int]) -> bool:
    values = set(ranks)
    if 14 in values:
        values.add(1)
    ordered = sorted(values)
    run = 1
    for previous, current in zip(ordered, ordered[1:], strict=False):
        if current == previous + 1:
            run += 1
            if run >= 5:
                return True
        elif current != previous:
            run = 1
    return False


def _position_adjust(observation: dict) -> float:
    position = str(observation.get("you", {}).get("position") or "")
    if position in _LATE:
        return _LATE[position]
    return _EARLY.get(position, 0.0)


def _rank(card: str) -> int:
    return _RANK.index(card[0]) + 2


def _int(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        return 0
    return value
