"""External-sampling MCCFR for one heads-up decision.

Same tree as the vanilla CFR solver: check or bet, then fold or call.
This is not a full-game solve and is never labeled Exact GTO.
"""

import random

from app.engine.cards import parse_cards
from app.solver.cfr import _average, _match, _values, _villain_average, hero_share
from app.solver.ranges import parse_range, remove_blockers
from app.solver.reference import (
    _bet_sizes,
    _facing_bet,
    _remember,
    _sampled_share,
    _unavailable,
    _unavailable_reason,
)
from app.solver.types import SolveRequest, SolveResult

_MAX_COMBOS = 80


class MccfrSolverAdapter:
    def health_check(self) -> dict:
        return {"status": "ok", "solver": "mccfr"}

    def solve_spot(self, request: SolveRequest) -> SolveResult:
        board_text = (request.board or "").strip()
        board = parse_cards(board_text) if board_text else []
        reason = _unavailable_reason(request, board)
        if reason is not None:
            return _unavailable(reason)
        dead = set(board)
        hero = remove_blockers(parse_range(request.hero_range), dead)[:_MAX_COMBOS]
        villain = remove_blockers(parse_range(request.villain_range), dead)[:_MAX_COMBOS]
        truncated = len(parse_range(request.hero_range)) > _MAX_COMBOS or len(
            parse_range(request.villain_range)
        ) > _MAX_COMBOS
        if not hero or not villain:
            return _unavailable("empty range")
        street = {3: "flop", 4: "turn", 5: "river"}[len(board)]
        exact = street == "river" and not truncated
        rng = random.Random(
            f"mccfr|{board_text}|{request.hero_range}|{request.villain_range}|{request.iterations}"
        )
        if exact:
            share_of = hero_share
            method = "mccfr"
        else:
            samples = max(1, request.samples)

            def share_of(left, right, cards, rng=rng, samples=samples):
                return _sampled_share(left, right, cards, samples, rng)

            method = "mccfr-monte-carlo"
        cached = _remember(share_of)
        to_call = _facing_bet(request)
        if to_call is not None:
            solved = _facing(
                hero,
                villain,
                board,
                request.pot,
                to_call,
                cached,
                request.iterations,
                rng,
            )
        else:
            solved = _check_or_bet(
                hero,
                villain,
                board,
                request.pot,
                _bet_sizes(request),
                cached,
                max(1, request.iterations),
                rng,
            )
        return SolveResult(
            actions=list(solved["actions"]),
            frequencies=dict(solved["frequencies"]),
            evs=dict(solved["evs"]),
            strategy=solved["strategy"],
            exploitability=solved["exploitability"],
            metadata={
                "solver": "mccfr",
                "label": "heads-up one-decision",
                "exact": exact,
                "mock": False,
                "available": True,
                "method": method,
                "street": street,
                "truncated": truncated,
            },
        )


def _check_or_bet(hero, villain, board, pot, bet_sizes, share_of, iterations, rng):
    actions = ["check", *[f"bet:{size}" for size in bet_sizes]]
    villain_actions = ["fold", "call"]
    hero_regret = {combo: dict.fromkeys(actions, 0.0) for combo in hero}
    hero_sum = {combo: dict.fromkeys(actions, 0.0) for combo in hero}
    villain_regret = {
        (combo, size): dict.fromkeys(villain_actions, 0.0)
        for combo in villain
        for size in bet_sizes
    }
    villain_sum = {
        (combo, size): dict.fromkeys(villain_actions, 0.0)
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
        return {
            "actions": actions,
            "frequencies": dict.fromkeys(actions, 1 / len(actions)),
            "evs": dict.fromkeys(actions, 0.0),
            "strategy": {"hero": {}, "villain": {}},
            "exploitability": None,
        }
    for step in range(iterations):
        left, right = pairs[rng.randrange(len(pairs))]
        if step % 2 == 0:
            _hero_sample(
                left,
                right,
                board,
                pot,
                actions,
                hero_regret,
                hero_sum,
                villain_regret,
                share_of,
                rng,
            )
        else:
            _villain_sample(
                left,
                right,
                board,
                pot,
                actions,
                hero_regret,
                villain_regret,
                villain_sum,
                share_of,
                rng,
            )
    hero_freq = _average(hero, hero_sum, actions)
    villain_freq = _villain_average(villain, bet_sizes, villain_sum)
    evs, _value, exploit = _values(
        pairs, board, pot, bet_sizes, actions, hero_sum, villain_sum, share_of
    )
    return {
        "actions": actions,
        "frequencies": hero_freq,
        "evs": evs,
        "strategy": {"hero": hero_freq, "villain": villain_freq},
        "exploitability": exploit,
    }


def _hero_sample(
    left,
    right,
    board,
    pot,
    actions,
    hero_regret,
    hero_sum,
    villain_regret,
    share_of,
    rng,
):
    strategy = _match(hero_regret[left], actions)
    utilities = {}
    for action in actions:
        if action == "check":
            utilities[action] = share_of(left, right, board) * pot
        else:
            size = int(action.split(":")[1])
            villain = _match(villain_regret[(right, size)], ["fold", "call"])
            drawn = _pick(villain, rng)
            share = share_of(left, right, board)
            utilities[action] = float(pot) if drawn == "fold" else share * (pot + 2 * size) - size
    node = sum(strategy[action] * utilities[action] for action in actions)
    for action in actions:
        hero_regret[left][action] += utilities[action] - node
        hero_sum[left][action] += strategy[action]


def _villain_sample(
    left,
    right,
    board,
    pot,
    actions,
    hero_regret,
    villain_regret,
    villain_sum,
    share_of,
    rng,
):
    strategy = _match(hero_regret[left], actions)
    drawn = _pick(strategy, rng)
    if drawn == "check":
        return
    size = int(drawn.split(":")[1])
    regret = villain_regret[(right, size)]
    total = villain_sum[(right, size)]
    response = _match(regret, ["fold", "call"])
    share = share_of(left, right, board)
    utilities = {"fold": float(pot), "call": share * (pot + 2 * size) - size}
    node = sum(response[action] * utilities[action] for action in utilities)
    for action in utilities:
        regret[action] += node - utilities[action]
        total[action] += response[action]


def _facing(hero, villain, board, pot, to_call, share_of, iterations, rng):
    actions = ["fold", "call"]
    pairs = [
        (left, right)
        for left in hero
        for right in villain
        if len({*left, *right, *board}) == 4 + len(board)
    ]
    regret = {combo: dict.fromkeys(actions, 0.0) for combo in hero}
    total = {combo: dict.fromkeys(actions, 0.0) for combo in hero}
    if not pairs or to_call <= 0:
        share = 1 / len(actions)
        frequencies = dict.fromkeys(actions, share)
        return {
            "actions": actions,
            "frequencies": frequencies,
            "evs": dict.fromkeys(actions, 0.0),
            "strategy": {"hero": frequencies, "villain": {}},
            "exploitability": None,
        }
    for _ in range(max(1, iterations)):
        left, right = pairs[rng.randrange(len(pairs))]
        share = share_of(left, right, board)
        utilities = {"fold": 0.0, "call": share * (pot + to_call) - to_call}
        strategy = _match(regret[left], actions)
        node = sum(strategy[action] * utilities[action] for action in actions)
        for action in actions:
            regret[left][action] += utilities[action] - node
            total[left][action] += strategy[action]
    frequencies = _average(hero, total, actions)
    call_ev = 0.0
    for left, right in pairs:
        share = share_of(left, right, board)
        call_ev += share * (pot + to_call) - to_call
    return {
        "actions": actions,
        "frequencies": frequencies,
        "evs": {"fold": 0.0, "call": call_ev / len(pairs)},
        "strategy": {"hero": frequencies, "villain": {}},
        "exploitability": 0.0,
    }


def _pick(strategy: dict[str, float], rng: random.Random) -> str:
    draw = rng.random()
    cursor = 0.0
    last = ""
    for action, weight in strategy.items():
        last = action
        cursor += weight
        if draw <= cursor:
            return action
    return last
