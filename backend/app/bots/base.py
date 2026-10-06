"""The observation contract. `decide` sees only what a human socket is sent."""

from dataclasses import dataclass


@dataclass(frozen=True)
class BotAction:
    """A choice the room still has to validate. `raise` amount is the street total."""

    kind: str
    amount: int | None = None


class PokerBot:
    def decide(self, observation: dict) -> BotAction:
        raise NotImplementedError


def legal_kinds(observation: dict) -> list[str]:
    kinds = observation.get("game", {}).get("legal_actions") or []
    return [kind for kind in kinds if isinstance(kind, str)]


def sized(observation: dict, kind: str) -> BotAction:
    """Pick a legal chip amount. Bet is chips put in. Raise is the street total."""
    if kind == "all_in":
        return BotAction("all_in")
    if kind not in {"bet", "raise"}:
        return BotAction(kind)
    game = observation.get("game", {})
    stack, committed = _own_chips(observation)
    ceiling = stack + committed
    if kind == "raise":
        minimum = game.get("min_raise_to")
        if not isinstance(minimum, int) or minimum > ceiling:
            return BotAction("all_in")
        pot = _positive(game.get("pot"))
        to_call = _positive(game.get("to_call"))
        target = max(minimum, committed + to_call + max(pot, minimum))
        if target > ceiling:
            return BotAction("all_in")
        return BotAction("raise", target)
    blind = _positive(game.get("big_blind")) or 1
    if blind > stack:
        return BotAction("all_in")
    return BotAction("bet", blind)


def _own_chips(observation: dict) -> tuple[int, int]:
    seat = observation.get("you", {}).get("seat")
    for player in observation.get("players", []):
        if player.get("seat") == seat:
            return _positive(player.get("stack")), _positive(player.get("committed_street"))
    return 0, 0


def _positive(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return 0
    return value


def safe_action(observation: dict) -> BotAction:
    legal = legal_kinds(observation)
    for kind in ("check", "call", "fold", "all_in"):
        if kind in legal:
            return sized(observation, kind)
    if legal:
        return sized(observation, legal[0])
    return BotAction("check")
