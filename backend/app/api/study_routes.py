"""Post-hand analysis and the trainer. These routes do not change a live hand."""

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.analysis.review import answer_spot, list_spots, review_hand, spot_prompt

router = APIRouter()


class AnswerBody(BaseModel):
    action: str


def _history(request: Request):
    return request.app.state.history


def _error(status: int, message: str) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        content={"type": "ERROR", "payload": {"message": message}},
    )


@router.get("/analyze/hands/{hand_id}")
def analyze_hand(
    hand_id: int,
    request: Request,
    good: float = 0.1,
    small: float = 0.5,
    medium: float = 2.0,
    large: float = 5.0,
):
    report = review_hand(
        _history(request),
        hand_id,
        good=good,
        small=small,
        medium=medium,
        large=large,
    )
    if report is None:
        return _error(404, "unknown hand")
    return report


@router.get("/trainer/spots")
def trainer_spots(
    request: Request,
    street: str | None = None,
    position: str | None = None,
    severity: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
) -> dict:
    return list_spots(
        _history(request),
        street=street,
        position=position,
        severity=severity,
        date_from=date_from,
        date_to=date_to,
    )


@router.get("/trainer/spots/{spot_id}")
def trainer_spot(spot_id: int, request: Request):
    prompt = spot_prompt(_history(request), spot_id)
    if prompt is None:
        return _error(404, "unknown trainer spot")
    return prompt


@router.post("/trainer/spots/{spot_id}/answer")
def trainer_answer(spot_id: int, body: AnswerBody, request: Request):
    try:
        revealed = answer_spot(_history(request), spot_id, body.action)
    except ValueError as exc:
        return _error(400, str(exc))
    if revealed is None:
        return _error(404, "unknown trainer spot")
    return revealed
