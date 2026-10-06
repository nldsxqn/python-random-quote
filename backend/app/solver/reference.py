"""Heads-up postflop, one decision. River enumerates. Earlier streets sample.

Nothing here is a full-game solve. Approximate output is never labeled Exact GTO.
"""

import random

from app.engine.cards import parse_cards, standard_deck
from app.solver.cfr import hero_share, solve_check_or_bet, solve_fold_or_call
from app.solver.ranges import parse_range, remove_blockers
from app.solver.types import SolveRequest, SolveResult

_MAX_COMBOS = 80


class ReferenceSolverAdapter:
    def health_check(self) -> dict:
        return {"status": "ok", "solver": "reference"}

    def solve_spot(self, request: SolveRequest) -> SolveResult:
        board_text = (request.board or "").strip()
        board = parse_cards(board_text) if board_text else []
        reason = _unavailable_reason(request, board)
        if reason is not None:
            return _unavailable(reason)
        dead = set(board)
        hero = remove_blockers(parse_range(request.hero_range), dead)
        villain = remove_blockers(parse_range(request.villain_range), dead)
        truncated = False
        if len(hero) > _MAX_COMBOS:
            hero = hero[:_MAX_COMBOS]
            truncated = True
        if len(villain) > _MAX_COMBOS:
            villain = villain[:_MAX_COMBOS]
            truncated = True
        if not hero or not villain:
            return _unavailable("empty range")
        street = {3: "flop", 4: "turn", 5: "river"}[len(board)]
        exact = street == "river" and not truncated
        if exact:
            share_of = hero_share
            method = "enumerate"
        else:
            rng = random.Random(
                f"{board_text}|{request.hero_range}|{request.villain_range}|{request.samples}"
            )
            samples = max(1, request.samples)

            def share_of(left, right, cards, rng=rng, samples=samples):
                return _sampled_share(left, right, cards, samples, rng)

            method = "monte_carlo"
        cached = _remember(share_of)
        to_call = _facing_bet(request)
        if to_call is not None:
            solved = solve_fold_or_call(
                hero,
                villain,
                board,
                request.pot,
                to_call,
                share_of=cached,
            )
        else:
            solved = solve_check_or_bet(
                hero,
                villain,
                board,
                request.pot,
                _bet_sizes(request),
                share_of=cached,
                iterations=max(1, request.iterations),
            )
        metadata = {
            "solver": "reference",
            "label": "heads-up one-decision",
            "exact": exact,
            "mock": False,
            "available": True,
            "method": method,
            "street": street,
            "truncated": truncated,
        }
        return SolveResult(
            actions=list(solved["actions"]),
            frequencies=dict(solved["frequencies"]),
            evs=dict(solved["evs"]),
            strategy=solved["strategy"],
            exploitability=solved["exploitability"],
            metadata=metadata,
        )


def _unavailable_reason(request: SolveRequest, board: list) -> str | None:
    if request.game_type != "nlhe":
        return "unsupported game"
    if request.players != 2:
        return "multiway"
    if len(board) < 3:
        return "preflop"
    if len(board) > 5:
        return "unsupported board"
    if not request.hero_range or not request.villain_range:
        return "empty range"
    return None


def _unavailable(reason: str) -> SolveResult:
    metadata = {
        "solver": "reference",
        "label": "unavailable",
        "exact": False,
        "mock": False,
        "available": False,
        "reason": reason,
    }
    return SolveResult(
        actions=[],
        frequencies={},
        evs={},
        strategy={},
        exploitability=None,
        metadata=metadata,
    )


def _bet_sizes(request: SolveRequest) -> list[int]:
    stack = request.effective_stack if request.effective_stack > 0 else 10**9
    raw = request.bet_sizes or [max(1, request.pot // 2), max(1, request.pot)]
    sizes: list[int] = []
    for size in raw:
        if isinstance(size, bool) or not isinstance(size, int):
            continue
        capped = min(size, stack)
        if capped > 0 and capped not in sizes:
            sizes.append(capped)
    return sizes or [min(max(1, request.pot), stack)]


def _facing_bet(request: SolveRequest) -> int | None:
    if not request.action_history:
        return None
    last = request.action_history[-1]
    if not isinstance(last, dict):
        return None
    action = str(last.get("action", ""))
    if action not in {"bet", "raise", "all_in"}:
        return None
    if request.hero_position and last.get("position") == request.hero_position:
        return None
    amount = last.get("to_call", last.get("amount"))
    if isinstance(amount, bool) or not isinstance(amount, int) or amount <= 0:
        return None
    return amount


def _sampled_share(hero, villain, board, samples: int, rng: random.Random) -> float:
    dead = {*hero, *villain, *board}
    remaining = [card for card in standard_deck() if card not in dead]
    need = 5 - len(board)
    if need <= 0:
        return hero_share(hero, villain, board)
    total = 0.0
    for _ in range(samples):
        total += hero_share(hero, villain, [*board, *rng.sample(remaining, need)])
    return total / samples


def _remember(share_of):
    cache: dict = {}

    def wrapped(hero, villain, board):
        key = (hero, villain)
        if key not in cache:
            cache[key] = share_of(hero, villain, board)
        return cache[key]

    return wrapped
