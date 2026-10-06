"""Frequencies on the acting player's turn. Heads-up postflop can use the reference tree."""

from app.solver.approx import APPROX_LABEL, approximate_mix
from app.solver.reference import ReferenceSolverAdapter
from app.solver.types import SolveRequest

_VILLAIN_RANGE = "JJ+,AQs,AKo"
_POSTFLOP = {"FLOP", "TURN", "RIVER"}


def study_advice(
    *,
    mode: str,
    in_hand: bool,
    player_count: int,
    street: str | None,
    board: list[str],
    pot: int,
    effective_stack: int,
    hero_cards: list[str],
    hero_position: str,
    to_call: int,
    cache: dict,
    legal_actions: list[str] | None = None,
    action_history: list | None = None,
    dealt_count: int | None = None,
    is_actor: bool = False,
    hero_seat: int | None = None,
    stacks: list[int] | None = None,
) -> dict | None:
    if not in_hand:
        return None
    if mode != "study" and not is_actor:
        return None
    dealt = player_count if dealt_count is None else dealt_count
    history = list(action_history or [])
    multiway = dealt >= 3 or player_count >= 3
    if (
        not multiway
        and player_count <= 2
        and street in _POSTFLOP
        and len(hero_cards) == 2
    ):
        solved = _reference_advice(
            street=street,
            board=board,
            pot=pot,
            effective_stack=effective_stack,
            hero_cards=hero_cards,
            hero_position=hero_position,
            to_call=to_call,
            cache=cache,
        )
        if solved.get("frequencies") and solved.get("metadata", {}).get("available", True):
            return solved
    return _approximate_advice(
        hero_cards=hero_cards,
        board=board,
        pot=pot,
        to_call=to_call,
        street=street,
        position=hero_position,
        action_history=history,
        legal_actions=list(legal_actions or []),
        player_count=max(player_count, 2),
        effective_stack=effective_stack,
        stacks=stacks,
        hero_seat=hero_seat,
        cache=cache,
    )


def _reference_advice(
    *,
    street: str | None,
    board: list[str],
    pot: int,
    effective_stack: int,
    hero_cards: list[str],
    hero_position: str,
    to_call: int,
    cache: dict,
) -> dict:
    key = ("reference", street, tuple(board), tuple(hero_cards), pot, to_call, effective_stack)
    cached = cache.get(key)
    if cached is not None:
        return cached
    history = [{"action": "bet", "amount": to_call}] if to_call > 0 else []
    request = SolveRequest(
        players=2,
        board=" ".join(board),
        pot=pot,
        effective_stack=max(effective_stack, to_call, 1),
        hero_position=hero_position,
        hero_range="".join(hero_cards),
        villain_range=_VILLAIN_RANGE,
        action_history=history,
        bet_sizes=_sizes(pot, effective_stack),
        iterations=24,
        samples=6,
    )
    result = ReferenceSolverAdapter().solve_spot(request)
    payload = result.to_dict()
    payload["assumption"] = f"villain range {_VILLAIN_RANGE}"
    cache[key] = payload
    return payload


def _approximate_advice(
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
    stacks: list[int] | None,
    hero_seat: int | None,
    cache: dict,
) -> dict:
    signature = tuple(
        (
            item.get("seat"),
            item.get("street"),
            item.get("action"),
            item.get("amount"),
            item.get("raised"),
        )
        for item in action_history
        if isinstance(item, dict)
    )
    key = (
        "approx",
        street,
        tuple(board),
        tuple(hero_cards),
        pot,
        to_call,
        effective_stack,
        position,
        tuple(legal_actions),
        signature,
        player_count,
        hero_seat,
        APPROX_LABEL,
    )
    cached = cache.get(key)
    if cached is not None:
        return cached
    payload = approximate_mix(
        hero_cards=hero_cards,
        board=board,
        pot=pot,
        to_call=to_call,
        street=street,
        position=position,
        action_history=action_history,
        legal_actions=legal_actions,
        player_count=player_count,
        effective_stack=effective_stack,
        stacks=stacks,
        hero_seat=hero_seat,
    )
    cache[key] = payload
    return payload


def _sizes(pot: int, stack: int) -> list[int]:
    half = max(1, pot // 2)
    full = max(half, pot)
    sizes: list[int] = []
    for size in (half, full):
        capped = min(size, stack) if stack > 0 else size
        if capped > 0 and capped not in sizes:
            sizes.append(capped)
    return sizes or [1]
