"""Study mode may show a mix during a heads-up hand. Competitive mode does not."""

from app.solver.reference import ReferenceSolverAdapter
from app.solver.types import SolveRequest

MULTIWAY_MESSAGE = (
    "Real-time multiway GTO analysis is not available. "
    "Post-hand analysis will be available after the hand."
)
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
) -> dict | None:
    if mode != "study" or not in_hand:
        return None
    if player_count >= 3:
        return {"message": MULTIWAY_MESSAGE}
    if len(hero_cards) != 2:
        return None
    if street not in _POSTFLOP:
        return {
            "message": "Preflop is not solved as exact GTO.",
            "metadata": {
                "solver": "reference",
                "label": "unavailable",
                "exact": False,
                "available": False,
                "reason": "preflop",
            },
        }
    key = (street, tuple(board), tuple(hero_cards), pot, to_call, effective_stack)
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


def _sizes(pot: int, stack: int) -> list[int]:
    half = max(1, pot // 2)
    full = max(half, pot)
    sizes: list[int] = []
    for size in (half, full):
        capped = min(size, stack) if stack > 0 else size
        if capped > 0 and capped not in sizes:
            sizes.append(capped)
    return sizes or [1]
