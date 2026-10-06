"""Explicit solves. A live competitive hand does not receive frequencies."""

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from app.solver.jobs import AnalysisStore
from app.solver.live import MULTIWAY_MESSAGE
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
    if body.during_hand and body.player_count >= 3:
        payload = {
            "message": MULTIWAY_MESSAGE,
            "metadata": {
                "solver": "reference",
                "label": "unavailable",
                "exact": False,
                "available": False,
                "reason": "multiway",
            },
        }
        _persist(request, None, payload, body)
        return payload
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
