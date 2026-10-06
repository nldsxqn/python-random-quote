"""Replay and statistics. These routes do not deal cards or change a live hand."""

import json

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from app.history.replay import hand_detail, list_hands, state_at
from app.history.stats import statistics

router = APIRouter()


def _history(request: Request):
    return request.app.state.history


def _error(status: int, message: str) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        content={"type": "ERROR", "payload": {"message": message}},
    )


@router.get("/hands")
def get_hands(request: Request, room_id: str | None = None, limit: int = 50) -> dict:
    return list_hands(_history(request), room_id=room_id, limit=limit)


@router.get("/hands/{hand_id}")
def get_hand(hand_id: int, request: Request, viewer_seat: int | None = None):
    detail = hand_detail(_history(request), hand_id, viewer_seat)
    if detail is None:
        return _error(404, "unknown hand")
    return detail


@router.get("/hands/{hand_id}/state")
def get_hand_state(
    hand_id: int,
    request: Request,
    index: int = 0,
    viewer_seat: int | None = None,
):
    try:
        state = state_at(_history(request), hand_id, index, viewer_seat)
    except IndexError:
        return _error(400, "action index is out of range")
    if state is None:
        return _error(404, "unknown hand")
    return state


@router.get("/stats")
def get_stats(
    request: Request,
    player: str | None = None,
    position: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    small_blind: int | None = None,
    big_blind: int | None = None,
    rules: str | None = None,
    street: str | None = None,
):
    try:
        return statistics(
            _history(request),
            player=player,
            position=position,
            date_from=date_from,
            date_to=date_to,
            small_blind=small_blind,
            big_blind=big_blind,
            rules=rules,
            street=street,
        )
    except json.JSONDecodeError:
        return _error(400, "rules filter must be a JSON object")
    except ValueError as exc:
        return _error(400, str(exc))
