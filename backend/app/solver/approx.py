"""Fast live mix from inferred ranges and a small equity sample.

This is not a solved game. metadata.exact stays false, and the label is never Exact GTO.
"""

import random

from app.engine.cards import Card, parse_card, standard_deck
from app.engine.evaluator import evaluate
from app.solver.ranges import parse_range

APPROX_LABEL = "Approximate frequencies, not exact GTO."
_SAMPLES = 28
_MAX_VILLAINS = 3
_KNOWN = ("fold", "check", "call", "bet", "raise", "all_in")
_WIDE = parse_range("22+,A2s+,K7s+,Q8s+,J8s+,T8s+,97s+,86s+,A8o+,KTo+,QTo+,JTo")
_CALLING = parse_range("44+,A7s+,K9s+,Q9s+,J9s+,T9s,A9o+,KJo+,QJo")
_TIGHT = parse_range("77+,ATs+,KJs+,QJs,AJo+,KQo")
_PREMIUM = parse_range("JJ+,AQs+,AKo")
_LATE = {"BTN", "CO", "HJ"}
_EARLY = {"UTG", "UTG1", "MP", "SB", "BB"}


def approximate_mix(
    *,
    hero_cards: list[str],
    board: list[str],
    pot: int,
    to_call: int,
    street: str | None,
    position: str,
    action_history: list,
    legal_actions: list[str],
    player_count: int,
    effective_stack: int,
    stacks: list[int] | None = None,
    hero_seat: int | None = None,
) -> dict:
    """Percents over the legal actions. A different holding or line can change the mix."""
    legal = _legal(legal_actions, to_call)
    hero = _hero(hero_cards)
    seen = _board(board)
    lines = _villain_lines(action_history, hero_seat, player_count)
    ranges = [_range_for(line) for line in lines]
    pressure = _pressure(line for line in lines)
    seed = "|".join(
        [
            ",".join(hero_cards),
            ",".join(board),
            street or "",
            position,
            str(pot),
            str(to_call),
            str(player_count),
            _history_text(action_history, hero_seat),
        ]
    )
    equity = _equity(hero, seen, ranges, random.Random(seed)) if hero is not None else 0.5
    prior = _prior(hero) if hero is not None else 0.5
    strength = min(0.98, max(0.02, 0.74 * equity + 0.26 * prior))
    odds = to_call / (pot + to_call) if to_call > 0 and pot + to_call > 0 else 0.0
    spr = _spr(pot, effective_stack, stacks)
    frequencies = _strategy(legal, strength, odds, pressure, position, spr)
    return {
        "actions": list(legal),
        "frequencies": frequencies,
        "evs": {},
        "metadata": {
            "solver": "approximate",
            "label": APPROX_LABEL,
            "exact": False,
            "mock": False,
            "available": True,
            "method": "range_equity",
            "street": street,
        },
    }


def _legal(actions: list[str] | None, to_call: int) -> list[str]:
    picked: list[str] = []
    for action in actions or []:
        if action in _KNOWN and action not in picked:
            picked.append(action)
    if picked:
        return picked
    if to_call > 0:
        return ["fold", "call", "raise", "all_in"]
    return ["check", "bet", "all_in"]


def _hero(cards: list[str]) -> tuple[Card, Card] | None:
    if len(cards) != 2:
        return None
    try:
        left, right = parse_card(cards[0]), parse_card(cards[1])
    except ValueError:
        return None
    if left == right:
        return None
    return left, right


def _board(cards: list[str]) -> list[Card]:
    seen: list[Card] = []
    for code in cards:
        try:
            seen.append(parse_card(code))
        except ValueError:
            continue
    return seen


def _villain_lines(history: list, hero_seat: int | None, player_count: int) -> list[list[dict]]:
    groups: dict[object, list[dict]] = {}
    order: list[object] = []
    for item in history:
        if not isinstance(item, dict):
            continue
        seat = item.get("seat")
        if hero_seat is not None and seat == hero_seat:
            continue
        key = seat if seat is not None else len(order)
        if key not in groups:
            groups[key] = []
            order.append(key)
        groups[key].append(item)
    lines = [groups[key] for key in order]
    villains = min(_MAX_VILLAINS, max(1, player_count - 1))
    while len(lines) < villains:
        lines.append([])
    return lines[:villains]


def _range_for(actions: list[dict]) -> list[tuple[Card, Card]]:
    bets = 0
    calls = 0
    for item in actions:
        kind = str(item.get("action", ""))
        raised = bool(item.get("raised"))
        if kind in {"bet", "raise"} or (kind == "all_in" and raised):
            bets += 1
        elif kind == "call" or (kind == "all_in" and not raised):
            calls += 1
    if bets >= 2:
        return _PREMIUM
    if bets >= 1:
        return _TIGHT
    if calls:
        return _CALLING
    return _WIDE


def _pressure(lines) -> float:
    score = 0.0
    for line in lines:
        for item in line:
            kind = str(item.get("action", ""))
            if kind in {"bet", "raise"} or (kind == "all_in" and item.get("raised")):
                score += 1.0 + _size_ratio(item)
            elif kind == "call":
                score += 0.2
    return min(1.0, score / 2.5)


def _size_ratio(item: dict) -> float:
    amount = item.get("amount", item.get("put_in"))
    pot_before = item.get("pot_before")
    if isinstance(amount, bool) or isinstance(pot_before, bool):
        return 0.0
    if not isinstance(amount, int) or not isinstance(pot_before, int) or pot_before <= 0:
        return 0.0
    return min(1.0, amount / pot_before)


def _history_text(history: list, hero_seat: int | None) -> str:
    parts: list[str] = []
    for item in history:
        if not isinstance(item, dict):
            continue
        if hero_seat is not None and item.get("seat") == hero_seat:
            continue
        parts.append(
            f"{item.get('seat')}:{item.get('street')}:{item.get('action')}:{item.get('amount')}"
        )
    return ",".join(parts)


def _equity(
    hero: tuple[Card, Card],
    board: list[Card],
    ranges: list[list[tuple[Card, Card]]],
    rng: random.Random,
) -> float:
    deck = standard_deck()
    base_dead = {hero[0], hero[1], *board}
    pools = []
    for combos in ranges:
        pool = [
            combo
            for combo in combos
            if combo[0] not in base_dead and combo[1] not in base_dead
        ]
        pools.append(pool)
    need = max(0, 5 - len(board))
    wins = 0.0
    trials = 0
    for _ in range(_SAMPLES):
        dead = set(base_dead)
        holes: list[tuple[Card, Card]] = []
        failed = False
        for pool in pools:
            combo = _draw(pool, dead, deck, rng)
            if combo is None:
                failed = True
                break
            holes.append(combo)
            dead.add(combo[0])
            dead.add(combo[1])
        if failed:
            continue
        rest = [card for card in deck if card not in dead]
        if len(rest) < need:
            continue
        runout = [*board, *rng.sample(rest, need)] if need else list(board)
        hero_rank = evaluate(hero, runout)
        ranks = [evaluate(hole, runout) for hole in holes]
        best = max(ranks)
        trials += 1
        if hero_rank > best:
            wins += 1.0
        elif hero_rank == best:
            tied = 1 + sum(rank == hero_rank for rank in ranks)
            wins += 1.0 / tied
    if trials == 0:
        return _prior(hero)
    return wins / trials


def _draw(
    pool: list[tuple[Card, Card]],
    dead: set[Card],
    deck: list[Card],
    rng: random.Random,
) -> tuple[Card, Card] | None:
    if pool:
        for _ in range(8):
            combo = pool[rng.randrange(len(pool))]
            if combo[0] not in dead and combo[1] not in dead:
                return combo
    rest = [card for card in deck if card not in dead]
    if len(rest) < 2:
        return None
    left, right = rng.sample(rest, 2)
    return left, right


def _prior(hero: tuple[Card, Card]) -> float:
    low, high = sorted((hero[0].rank, hero[1].rank))
    if low == high:
        return 0.55 + (high - 2) / 12 * 0.4
    gap = high - low - 1
    suited = hero[0].suit == hero[1].suit
    score = 0.08 + ((high - 2) / 12) * 0.55
    if gap <= 1:
        score += 0.08
    if suited:
        score += 0.06
    return min(0.85, max(0.05, score))


def _spr(pot: int, effective_stack: int, stacks: list[int] | None) -> float:
    stack = effective_stack
    if stacks:
        positive = [value for value in stacks if isinstance(value, int) and value > 0]
        if positive:
            stack = min(positive)
    if pot <= 0:
        return 20.0
    return max(stack, 0) / pot


def _strategy(
    legal: list[str],
    strength: float,
    pot_odds: float,
    pressure: float,
    position: str,
    spr: float,
) -> dict[str, float]:
    late = 0.06 if position in _LATE else 0.0
    early = -0.04 if position in _EARLY else 0.0
    edge = strength - pot_odds + late + early
    raw: dict[str, float] = {}
    for action in legal:
        if action == "fold":
            raw[action] = 0.15 + max(0.0, 0.55 - edge) * (1 + 0.8 * pressure)
        elif action == "check":
            raw[action] = 0.35 + (1 - abs(strength - 0.48)) * 0.25 + pressure * 0.5
        elif action == "call":
            raw[action] = 0.2 + max(0.0, edge + 0.25) * (1 - 0.35 * pressure)
        elif action == "bet":
            raw[action] = 0.12 + max(0.0, strength - 0.28 + late) * (1.15 - 0.7 * pressure)
        elif action == "raise":
            raw[action] = 0.08 + max(0.0, strength - 0.48 + late) * (1.2 - 0.85 * pressure)
        elif action == "all_in":
            short = 0.35 if spr < 3 else 0.0
            raw[action] = 0.05 + max(0.0, strength - 0.62) * 1.4 + short * strength
        else:
            raw[action] = 0.05
        raw[action] = max(0.02, raw[action])
    total = sum(raw.values())
    frequencies = {action: weight / total for action, weight in raw.items()}
    last = legal[-1]
    frequencies[last] += 1.0 - sum(frequencies.values())
    return frequencies
