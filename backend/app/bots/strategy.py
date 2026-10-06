"""Look up a saved mix. A miss is played by EquityBot."""

import json
import random
from dataclasses import dataclass
from pathlib import Path

from app.bots.base import BotAction, PokerBot, legal_kinds, sized
from app.bots.equity_bot import EquityBot

_FIXTURE = Path(__file__).with_name("fixtures") / "btn_open.json"


@dataclass(frozen=True)
class StrategySpot:
    small_blind: int
    big_blind: int
    position: str
    stack_bb: int
    board: tuple[str, ...]
    history: tuple[tuple[str, int | None], ...]
    mix: dict[str, float]
    raise_to: int | None = None
    bet_amount: int | None = None


class StrategyStore:
    def __init__(self, spots: list[StrategySpot]) -> None:
        self.spots = spots

    def lookup(self, observation: dict) -> StrategySpot | None:
        key = spot_key(observation)
        for spot in self.spots:
            if (
                spot.small_blind == key[0]
                and spot.big_blind == key[1]
                and spot.position == key[2]
                and spot.stack_bb == key[3]
                and spot.board == key[4]
                and spot.history == key[5]
            ):
                return spot
        return None


class StrategyBot(PokerBot):
    def __init__(self, store: StrategyStore, fallback: EquityBot, seed: int = 0) -> None:
        self.store = store
        self.fallback = fallback
        self.rng = random.Random(seed)

    def decide(self, observation: dict) -> BotAction:
        spot = self.store.lookup(observation)
        if spot is None:
            return self.fallback.decide(observation)
        kind = _sample(spot.mix, self.rng)
        legal = legal_kinds(observation)
        if kind not in legal:
            ranked = sorted(spot.mix, key=lambda name: spot.mix[name], reverse=True)
            kind = next((name for name in ranked if name in legal), "")
            if not kind:
                return self.fallback.decide(observation)
        fits = spot.raise_to is not None and _raise_fits(observation, spot.raise_to)
        if kind == "raise" and fits:
            return BotAction("raise", spot.raise_to)
        if kind == "bet" and spot.bet_amount is not None:
            return BotAction("bet", spot.bet_amount)
        return sized(observation, kind)


def load_fixture_store(path: Path | None = None) -> StrategyStore:
    raw = json.loads((path or _FIXTURE).read_text())
    spots = [_spot(item) for item in raw["entries"]]
    return StrategyStore(spots)


def spot_key(observation: dict) -> tuple:
    settings = observation.get("settings", {})
    game = observation.get("game", {})
    you = observation.get("you", {})
    small = _int(settings.get("small_blind"))
    big = _int(game.get("big_blind") or settings.get("big_blind"))
    depth = _stack_bb(observation, big)
    board = tuple(game.get("board") or [])
    history = tuple(
        (str(item.get("action")), _optional_int(item.get("amount")))
        for item in game.get("action_history") or []
    )
    return (small, big, str(you.get("position") or ""), depth, board, history)


def _spot(item: dict) -> StrategySpot:
    history = tuple(
        (str(row["action"]), _optional_int(row.get("amount"))) for row in item["history"]
    )
    return StrategySpot(
        small_blind=item["game"]["small_blind"],
        big_blind=item["game"]["big_blind"],
        position=item["position"],
        stack_bb=item["stack_bb"],
        board=tuple(item["board"]),
        history=history,
        mix={str(name): float(weight) for name, weight in item["mix"].items()},
        raise_to=item.get("raise_to"),
        bet_amount=item.get("bet_amount"),
    )


def _sample(mix: dict[str, float], rng: random.Random) -> str:
    names = list(mix)
    total = sum(mix.values())
    if total <= 0 or not names:
        return names[0] if names else "check"
    mark = rng.random() * total
    cursor = 0.0
    for name in names:
        cursor += mix[name]
        if mark <= cursor:
            return name
    return names[-1]


def _raise_fits(observation: dict, amount: int) -> bool:
    game = observation.get("game", {})
    minimum = game.get("min_raise_to")
    if isinstance(minimum, int) and amount < minimum:
        return False
    seat = observation.get("you", {}).get("seat")
    for player in observation.get("players", []):
        if player.get("seat") != seat:
            continue
        room = _int(player.get("stack")) + _int(player.get("committed_street"))
        return amount <= room
    return False


def _stack_bb(observation: dict, big_blind: int) -> int:
    if big_blind <= 0:
        return 0
    seat = observation.get("you", {}).get("seat")
    for player in observation.get("players", []):
        if player.get("seat") == seat:
            chips = _int(player.get("stack")) + _int(player.get("committed_hand"))
            return chips // big_blind
    return 0


def _optional_int(value: object) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value


def _int(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        return 0
    return value
