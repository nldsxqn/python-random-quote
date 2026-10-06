"""Explicit solves. A live competitive hand does not receive frequencies."""

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from app.solver.approx import approximate_mix
from app.solver.jobs import AnalysisStore
from app.solver.mccfr import MccfrSolverAdapter
from app.solver.mock import MockSolverAdapter
from app.solver.reference import ReferenceSolverAdapter
from app.solver.types import SolveRequest
from app.solver.zeta import ZetaAdapter

router = APIRouter()


class SolveBody(BaseModel):
    game_type: str = "nlhe"
    players: int = 2
    board: str = ""
    pot: int = 0
    effective_stack: int = 0
    hero_position: str = ""
    villain_position: str = ""
    hero_range: str = ""
    villain_range: str = ""
    action_history: list = Field(default_factory=list)
    bet_sizes: list = Field(default_factory=list)
    iterations: int = 40
    samples: int = 8
    adapter: str = "reference"
    mode: str = "posthand"
    during_hand: bool = False
    player_count: int = 2
    room_id: str | None = None
    hand_id: int | None = None


@router.get("/solver/health")
def solver_health(adapter: str = "mock") -> dict:
    return _adapter(adapter).health_check()


@router.post("/solver/solve")
def solve_spot(body: SolveBody, request: Request) -> dict:
    if body.during_hand and body.mode != "study":
        payload = {
            "message": "Competitive mode hides the mix during the hand.",
            "metadata": {
                "solver": body.adapter,
                "label": "withheld",
                "exact": False,
                "mock": False,
                "withheld": True,
                "mode": "competitive",
            },
        }
        _persist(request, None, payload, body)
        return payload
    if body.during_hand and body.player_count >= 3:
        payload = approximate_mix(
            hero_cards=_hero_cards(body.hero_range),
            board=[part for part in body.board.split() if part],
            pot=body.pot,
            to_call=_posted_call(body.action_history),
            street=_street_name(body.board),
            position=body.hero_position,
            action_history=list(body.action_history),
            legal_actions=[],
            player_count=body.player_count,
            effective_stack=body.effective_stack,
        )
        _persist(request, None, payload, body)
        return payload
    spot = SolveRequest(
        game_type=body.game_type,
        players=body.players,
        board=body.board,
        pot=body.pot,
        effective_stack=body.effective_stack,
        hero_position=body.hero_position,
        villain_position=body.villain_position,
        hero_range=body.hero_range,
        villain_range=body.villain_range,
        action_history=list(body.action_history),
        bet_sizes=list(body.bet_sizes),
        iterations=body.iterations,
        samples=body.samples,
    )
    try:
        result = _adapter(body.adapter).solve_spot(spot)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    payload = result.to_dict()
    _persist(request, spot, payload, body)
    return payload


def _adapter(name: str):
    if name == "mock":
        return MockSolverAdapter()
    if name == "reference":
        return ReferenceSolverAdapter()
    if name == "mccfr":
        return MccfrSolverAdapter()
    if name == "zeta":
        return ZetaAdapter()
    raise HTTPException(status_code=400, detail="unknown solver adapter")


def _hero_cards(hero_range: str) -> list[str]:
    raw = hero_range.replace(",", " ").split()
    cards = [part for part in raw if len(part) == 2]
    if len(cards) >= 2:
        return cards[:2]
    compact = hero_range.replace(" ", "")
    if len(compact) == 4:
        return [compact[:2], compact[2:]]
    return []


def _posted_call(history: list) -> int:
    if not history:
        return 0
    last = history[-1]
    if not isinstance(last, dict):
        return 0
    if str(last.get("action", "")) not in {"bet", "raise", "all_in"}:
        return 0
    amount = last.get("to_call", last.get("amount"))
    if isinstance(amount, bool) or not isinstance(amount, int) or amount <= 0:
        return 0
    return amount


def _street_name(board: str) -> str:
    count = len([part for part in board.split() if part])
    return {0: "PREFLOP", 3: "FLOP", 4: "TURN", 5: "RIVER"}.get(count, "PREFLOP")


def _persist(request: Request, spot: SolveRequest | None, payload: dict, body: SolveBody) -> None:
    store = getattr(request.app.state, "analysis", None)
    if not isinstance(store, AnalysisStore):
        return
    store.save_job(
        spot,
        payload,
        mode=body.mode,
        room_id=body.room_id,
        hand_id=body.hand_id,
        message=payload.get("message"),
    )
