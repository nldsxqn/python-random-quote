"""Monte Carlo equity against the price the pot is offering."""

import random

from app.bots.base import BotAction, PokerBot, legal_kinds, safe_action, sized
from app.engine.cards import parse_card, standard_deck
from app.engine.evaluator import evaluate

_LATE = {"BTN", "CO", "HJ"}


class EquityBot(PokerBot):
    def __init__(
        self,
        *,
        tightness: float = 0.05,
        aggression: float = 0.4,
        bluff_frequency: float = 0.05,
        simulation_count: int = 40,
        seed: int = 0,
    ) -> None:
        self.tightness = tightness
        self.aggression = aggression
        self.bluff_frequency = bluff_frequency
        self.simulation_count = simulation_count
        self.rng = random.Random(seed)

    def decide(self, observation: dict) -> BotAction:
        legal = legal_kinds(observation)
        if not legal:
            return safe_action(observation)
        equity = self.equity(observation)
        game = observation.get("game", {})
        to_call = _int(game.get("to_call"))
        pot = _int(game.get("pot"))
        price = to_call / (pot + to_call) if to_call > 0 else 0.0
        required = min(0.95, price + self.tightness * 0.2)
        position = str(observation.get("you", {}).get("position") or "")
        if position in _LATE:
            required = max(0.0, required - 0.04)
        spr = _spr(observation)
        if spr < 2 and equity >= 0.55 and "all_in" in legal and equity >= required:
            return BotAction("all_in")
        margin = equity - required
        if margin >= 0.12 * max(self.aggression, 0.1) and "raise" in legal:
            return sized(observation, "raise")
        if margin >= 0.08 and "bet" in legal and to_call <= 0:
            return sized(observation, "bet")
        if equity >= required and "call" in legal:
            return BotAction("call")
        if equity >= required and "check" in legal:
            return BotAction("check")
        if (
            to_call <= 0
            and "bet" in legal
            and self.rng.random() < self.bluff_frequency
            and position in _LATE
        ):
            return sized(observation, "bet")
        if "check" in legal:
            return BotAction("check")
        if "fold" in legal:
            return BotAction("fold")
        return safe_action(observation)

    def equity(self, observation: dict) -> float:
        holes = observation.get("you", {}).get("hole_cards") or []
        board = list(observation.get("game", {}).get("board") or [])
        if len(holes) != 2 or self.simulation_count <= 0:
            return 0.0
        known = {_code(card) for card in [*holes, *board]}
        remaining = [card for card in standard_deck() if card.code not in known]
        villains = _villain_count(observation)
        if villains <= 0:
            return 1.0
        need = villains * 2 + max(0, 5 - len(board))
        if len(remaining) < need:
            return 0.0
        hero = (parse_card(holes[0]), parse_card(holes[1]))
        seen_board = [parse_card(card) for card in board]
        won = 0.0
        for _ in range(self.simulation_count):
            draw = remaining[:]
            self.rng.shuffle(draw)
            cursor = 0
            villain_holes = []
            for _villain in range(villains):
                villain_holes.append((draw[cursor], draw[cursor + 1]))
                cursor += 2
            run = seen_board + draw[cursor : cursor + (5 - len(seen_board))]
            hero_rank = evaluate(hero, run)
            ranks = [evaluate(hole, run) for hole in villain_holes]
            best = max(ranks)
            if hero_rank > best:
                won += 1
            elif hero_rank == best:
                tied = 1 + sum(rank == hero_rank for rank in ranks)
                won += 1 / tied
        return won / self.simulation_count


def _villain_count(observation: dict) -> int:
    seat = observation.get("you", {}).get("seat")
    count = 0
    for player in observation.get("players", []):
        if player.get("seat") == seat:
            continue
        if player.get("status") in {"ACTIVE", "ALL_IN"}:
            count += 1
    return count


def _spr(observation: dict) -> float:
    you = observation.get("you", {})
    seat = you.get("seat")
    own = 0
    others: list[int] = []
    for player in observation.get("players", []):
        stack = _int(player.get("stack"))
        if player.get("seat") == seat:
            own = stack
        elif player.get("status") in {"ACTIVE", "ALL_IN"}:
            others.append(stack)
    pot = _int(observation.get("game", {}).get("pot"))
    if pot <= 0:
        return 99.0
    effective = own if not others else min(own, max(others))
    return effective / pot


def _code(card: str) -> str:
    return card


def _int(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        return 0
    return value
