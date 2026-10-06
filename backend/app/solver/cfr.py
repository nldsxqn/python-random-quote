"""Vanilla CFR for one heads-up decision: check or bet, then fold or call.

This is not a full-game solver and must not be labeled Exact GTO.
"""

from app.engine.cards import Card
from app.engine.evaluator import evaluate


def hero_share(hero: tuple[Card, Card], villain: tuple[Card, Card], board: list[Card]) -> float:
    left = evaluate(hero, board)
    right = evaluate(villain, board)
    if left > right:
        return 1.0
    if left < right:
        return 0.0
    return 0.5


def solve_check_or_bet(
    hero: list[tuple[Card, Card]],
    villain: list[tuple[Card, Card]],
    board: list[Card],
    pot: int,
    bet_sizes: list[int],
    *,
    share_of,
    iterations: int,
) -> dict:
    """`share_of(hero, villain, board)` is 1, 0, or a fraction. River passes hero_share."""
    actions = ["check", *[f"bet:{size}" for size in bet_sizes]]
    hero_regret = {combo: {action: 0.0 for action in actions} for combo in hero}
    hero_sum = {combo: {action: 0.0 for action in actions} for combo in hero}
    villain_actions = ["fold", "call"]
    villain_regret = {
        (combo, size): {action: 0.0 for action in villain_actions}
        for combo in villain
        for size in bet_sizes
    }
    villain_sum = {
        (combo, size): {action: 0.0 for action in villain_actions}
        for combo in villain
        for size in bet_sizes
    }
    pairs = [
        (left, right)
        for left in hero
        for right in villain
        if len({*left, *right, *board}) == 4 + len(board)
    ]
    if not pairs or pot < 0:
        return _empty(actions)
    for _ in range(max(1, iterations)):
        for left, right in pairs:
            _walk_hero(
                left,
                right,
                board,
                pot,
                bet_sizes,
                actions,
                hero_regret,
                hero_sum,
                villain_regret,
                villain_sum,
                share_of,
            )
    hero_freq = _average(hero, hero_sum, actions)
    villain_freq = _villain_average(villain, bet_sizes, villain_sum)
    evs, value, exploit = _values(
        pairs,
        board,
        pot,
        bet_sizes,
        actions,
        hero_sum,
        villain_sum,
        share_of,
    )
    return {
        "actions": actions,
        "frequencies": hero_freq,
        "evs": evs,
        "strategy": {"hero": hero_freq, "villain": villain_freq},
        "exploitability": exploit,
        "value": value,
    }


def solve_fold_or_call(
    hero: list[tuple[Card, Card]],
    villain: list[tuple[Card, Card]],
    board: list[Card],
    pot: int,
    to_call: int,
    *,
    share_of,
) -> dict:
    """Villain has already bet. Hero calls when the call EV is higher than folding."""
    actions = ["fold", "call"]
    pairs = [
        (left, right)
        for left in hero
        for right in villain
        if len({*left, *right, *board}) == 4 + len(board)
    ]
    if not pairs or to_call <= 0:
        return _empty(actions)
    fold_mass = 0.0
    call_mass = 0.0
    call_ev = 0.0
    for left, right in pairs:
        share = share_of(left, right, board)
        ev_call = share * (pot + to_call) - to_call
        if ev_call > 0:
            call_mass += 1
            call_ev += ev_call
        elif ev_call < 0:
            fold_mass += 1
        else:
            fold_mass += 0.5
            call_mass += 0.5
    total = fold_mass + call_mass
    frequencies = {"fold": fold_mass / total, "call": call_mass / total}
    evs = {
        "fold": 0.0,
        "call": call_ev / len(pairs),
    }
    return {
        "actions": actions,
        "frequencies": frequencies,
        "evs": evs,
        "strategy": {"hero": frequencies, "villain": {}},
        "exploitability": 0.0,
        "value": (call_mass / total) * (call_ev / len(pairs)),
    }


def _walk_hero(
    left,
    right,
    board,
    pot,
    bet_sizes,
    actions,
    hero_regret,
    hero_sum,
    villain_regret,
    villain_sum,
    share_of,
) -> float:
    strategy = _match(hero_regret[left], actions)
    utilities = {}
    for action in actions:
        if action == "check":
            utilities[action] = share_of(left, right, board) * pot
        else:
            size = int(action.split(":")[1])
            utilities[action] = _villain_value(
                left,
                right,
                board,
                pot,
                size,
                villain_regret[(right, size)],
                villain_sum[(right, size)],
                share_of,
            )
    node = sum(strategy[action] * utilities[action] for action in actions)
    for action in actions:
        hero_regret[left][action] += utilities[action] - node
        hero_sum[left][action] += strategy[action]
    return node


def _villain_value(left, right, board, pot, size, regret, total, share_of) -> float:
    strategy = _match(regret, ["fold", "call"])
    share = share_of(left, right, board)
    utilities = {
        "fold": float(pot),
        "call": share * (pot + 2 * size) - size,
    }
    node = sum(strategy[action] * utilities[action] for action in utilities)
    for action in utilities:
        regret[action] += node - utilities[action]
        total[action] += strategy[action]
    return node


def _match(regret: dict[str, float], actions: list[str]) -> dict[str, float]:
    positive = {action: max(0.0, regret[action]) for action in actions}
    total = sum(positive.values())
    if total <= 0:
        share = 1 / len(actions)
        return dict.fromkeys(actions, share)
    return {action: positive[action] / total for action in actions}


def _average(combos, totals, actions) -> dict[str, float]:
    mass = {action: 0.0 for action in actions}
    weight = 0.0
    for combo in combos:
        for action in actions:
            mass[action] += totals[combo][action]
            weight += totals[combo][action]
    if weight <= 0:
        share = 1 / len(actions)
        return dict.fromkeys(actions, share)
    return {action: mass[action] / weight for action in actions}


def _villain_average(combos, sizes, totals) -> dict[str, float]:
    mass = {"fold": 0.0, "call": 0.0}
    weight = 0.0
    for combo in combos:
        for size in sizes:
            for action in ("fold", "call"):
                mass[action] += totals[(combo, size)][action]
                weight += totals[(combo, size)][action]
    if weight <= 0:
        return {"fold": 0.5, "call": 0.5}
    return {action: mass[action] / weight for action in mass}


def _values(pairs, board, pot, bet_sizes, actions, hero_sum, villain_sum, share_of) -> tuple:
    evs = dict.fromkeys(actions, 0.0)
    current = 0.0
    best = 0.0
    response = 0.0
    for left, right in pairs:
        strategy = _average_one(hero_sum[left], actions)
        utilities = {}
        for action in actions:
            if action == "check":
                utilities[action] = share_of(left, right, board) * pot
            else:
                size = int(action.split(":")[1])
                villain = _average_one(villain_sum[(right, size)], ["fold", "call"])
                share = share_of(left, right, board)
                fold_ev = float(pot)
                call_ev = share * (pot + 2 * size) - size
                utilities[action] = villain["fold"] * fold_ev + villain["call"] * call_ev
                best_villain = min(fold_ev, call_ev)
                response += strategy[action] * best_villain
        for action in actions:
            evs[action] += utilities[action]
        mix = sum(strategy[action] * utilities[action] for action in actions)
        current += mix
        best += max(utilities.values())
    count = len(pairs)
    evs = {action: evs[action] / count for action in actions}
    current /= count
    best /= count
    response /= count
    return evs, current, max(0.0, best - current) + max(0.0, current - response)


def _average_one(total: dict[str, float], actions: list[str]) -> dict[str, float]:
    weight = sum(total[action] for action in actions)
    if weight <= 0:
        share = 1 / len(actions)
        return dict.fromkeys(actions, share)
    return {action: total[action] / weight for action in actions}


def _empty(actions: list[str]) -> dict:
    share = 1 / len(actions) if actions else 0
    frequencies = dict.fromkeys(actions, share)
    return {
        "actions": actions,
        "frequencies": frequencies,
        "evs": dict.fromkeys(actions, 0.0),
        "strategy": {"hero": frequencies, "villain": {}},
        "exploitability": None,
        "value": 0.0,
    }
