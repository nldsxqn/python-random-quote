"""Persist an explicit solve. Views do not write these rows."""

from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.database.models import AnalysisJob, DecisionAnalysis
from app.solver.types import SolveRequest


class AnalysisStore:
    def __init__(self, engine) -> None:
        self.engine = engine

    def save_job(
        self,
        request: SolveRequest | None,
        result: dict,
        *,
        mode: str | None,
        room_id: str | None = None,
        hand_id: int | None = None,
        message: str | None = None,
    ) -> int:
        metadata = result.get("metadata") or {}
        frequencies = result.get("frequencies") or {}
        evs = result.get("evs") or {}
        chosen = max(frequencies, key=frequencies.get) if frequencies else None
        best = max(evs.values()) if evs else None
        with Session(self.engine) as session:
            job = AnalysisJob(
                created_at=datetime.now(UTC).isoformat(),
                status="complete",
                adapter=metadata.get("solver"),
                mode=mode,
                exact=metadata.get("exact"),
                label=metadata.get("label"),
                room_id=room_id,
                hand_id=hand_id,
                message=message if message is not None else metadata.get("message"),
                request_json=None if request is None else request.to_dict(),
                result_json=result,
            )
            session.add(job)
            session.flush()
            session.add(
                DecisionAnalysis(
                    job_id=job.id,
                    hand_id=hand_id,
                    street=_street(request),
                    position=None if request is None else request.hero_position,
                    action=chosen,
                    ev=best,
                    payload={"frequencies": frequencies, "evs": evs},
                )
            )
            session.commit()
            return int(job.id)


def _street(request: SolveRequest | None) -> str | None:
    if request is None:
        return None
    count = len(request.board.split()) if request.board.strip() else 0
    return {3: "flop", 4: "turn", 5: "river"}.get(count, "preflop")
