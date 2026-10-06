"""Rebuild a stored hand and score the important decisions.

EV loss in big blinds is the best action EV minus the EV of the action taken.
Multiway scores are Approximate Analysis. They are never Exact GTO.
"""

from datetime import UTC, datetime

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.database.models import (
    ActionRow,
    AnalysisJob,
    BoardRow,
    DecisionAnalysis,
    Hand,
    HandPlayer,
    TrainerSpot,
)
from app.engine.cards import parse_cards
from app.history.store import HandHistory
from app.solver.ranges import matrix, parse_range, remove_blockers
from app.solver.reference import ReferenceSolverAdapter
from app.solver.types import SolveRequest

VILLAIN_RANGE = "JJ+,AQs,AKo"
LARGE_POT_BB = 10
_ASSUMPTION = f"villain range {VILLAIN_RANGE}"


def classify_loss(
    loss_bb: float,
    *,
    good: float = 0.1,
    small: float = 0.5,
    medium: float = 2.0,
    large: float = 5.0,
) -> str:
    """Under `good` is Good. Each later bound is the start of the next label.

    0.1 is Small, 0.5 is Medium, and 2 and 5 are Large. Above `large` is Critical.
    """
    if loss_bb < good:
        return "Good"
    if loss_bb < small:
        return "Small"
    if loss_bb < medium:
        return "Medium"
    if loss_bb <= large:
        return "Large"
    return "Critical"


def review_hand(
    history: HandHistory,
    hand_id: int,
    *,
    good: float = 0.1,
    small: float = 0.5,
    medium: float = 2.0,
    large: float = 5.0,
) -> dict | None:
    with history.sessions() as session:
        hand = session.get(Hand, hand_id)
        if hand is None:
            return None
        players = list(
            session.scalars(
                select(HandPlayer).where(HandPlayer.hand_id == hand.id).order_by(HandPlayer.seat)
            )
        )
        actions = list(
            session.scalars(
                select(ActionRow)
                .where(ActionRow.hand_id == hand.id)
                .order_by(ActionRow.order_index)
            )
        )
        boards = list(
            session.scalars(
                select(BoardRow).where(BoardRow.hand_id == hand.id).order_by(BoardRow.run_index)
            )
        )
        report = _review(
            hand,
            players,
            actions,
            boards,
            good=good,
            small=small,
            medium=medium,
            large=large,
        )
    _persist(history.engine, hand_id, report)
    return report


def list_spots(
    history: HandHistory,
    *,
    street: str | None = None,
    position: str | None = None,
    severity: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
) -> dict:
    with history.sessions() as session:
        query = select(TrainerSpot).order_by(TrainerSpot.id.desc())
        if street:
            query = query.where(TrainerSpot.street == street.upper())
        if position:
            query = query.where(TrainerSpot.position == position.upper())
        if severity:
            query = query.where(TrainerSpot.severity == severity)
        if date_from:
            query = query.where(TrainerSpot.decided_at >= date_from)
        if date_to:
            end = f"{date_to}T23:59:59.999999" if len(date_to) == 10 else date_to
            query = query.where(TrainerSpot.decided_at <= end)
        rows = list(session.scalars(query))
        return {"spots": [_public_spot(row) for row in rows]}


def spot_prompt(history: HandHistory, spot_id: int) -> dict | None:
    with history.sessions() as session:
        row = session.get(TrainerSpot, spot_id)
        if row is None:
            return None
        return _public_spot(row)


def answer_spot(history: HandHistory, spot_id: int, action: str) -> dict | None:
    with history.sessions() as session:
        row = session.get(TrainerSpot, spot_id)
        if row is None:
            return None
        stored = dict(row.spot_json or {})
        choices = list((stored.get("prompt") or {}).get("actions") or [])
        if action not in choices:
            raise ValueError("that action is not in this spot")
        answer = dict(stored.get("answer") or {})
        return {
            "id": row.id,
            "your_action": action,
            "frequencies": answer.get("frequencies") or {},
            "evs": answer.get("evs") or {},
            "original_action": answer.get("original_action"),
            "ev_loss": answer.get("ev_loss"),
            "strategy": answer.get("strategy") or {},
            "matrix": answer.get("matrix") or [],
            "metadata": answer.get("metadata") or {},
        }


def _review(hand, players, actions, boards, **bounds) -> dict:
    shared = list(boards[0].cards) if boards else []
    by_seat = {player.seat: player for player in players}
    active = set(by_seat)
    stacks = {player.seat: player.stack_after_posts for player in players}
    street_put: dict[int, int] = {}
    current_street = None
    preflop_raises = 0
    three_bet = False
    nodes: list[dict] = []
    decisions: list[dict] = []
    for action in actions:
        if action.street != current_street:
            current_street = action.street
            street_put = {}
        reasons = _reasons(action, hand.big_blind, three_bet, preflop_raises)
        table = _table(action, shared, by_seat, stacks, active)
        scored = None
        if reasons:
            scored = _score(
                action,
                by_seat,
                shared,
                street_put,
                active,
                hand.big_blind,
                table,
                bounds,
            )
            scored["reasons"] = reasons
            decisions.append(scored)
        nodes.append(
            {
                "street": action.street,
                "seat": action.seat,
                "position": by_seat[action.seat].position,
                "action": action.action,
                "amount": action.amount,
                "pot": action.pot_before,
                "reasons": reasons,
            }
        )
        stacks[action.seat] = stacks.get(action.seat, 0) - action.put_in
        street_put[action.seat] = street_put.get(action.seat, 0) + action.put_in
        if action.action == "fold":
            active.discard(action.seat)
        if action.street == "PREFLOP" and action.raised:
            preflop_raises += 1
            if preflop_raises >= 2:
                three_bet = True
    return {
        "hand_id": hand.id,
        "room_id": hand.room_id,
        "big_blind": hand.big_blind,
        "board": shared,
        "players": [
            {
                "seat": player.seat,
                "nickname": player.nickname,
                "position": player.position,
                "hole_cards": list(player.hole_cards),
                "starting_stack": player.starting_stack,
                "ending_stack": player.ending_stack,
            }
            for player in players
        ],
        "tree": _chain(nodes),
        "decisions": decisions,
        "thresholds": {
            "good": bounds["good"],
            "small": bounds["small"],
            "medium": bounds["medium"],
            "large": bounds["large"],
        },
    }


def _reasons(action, big_blind: int, three_bet: bool, preflop_raises: int) -> list[str]:
    bb = big_blind if big_blind else 1
    reasons: list[str] = []
    if action.pot_before >= LARGE_POT_BB * bb:
        reasons.append("large pot")
    if action.put_in >= LARGE_POT_BB * bb or (
        action.pot_before > 0 and action.put_in >= action.pot_before and action.put_in > 0
    ):
        reasons.append("large bet")
    if action.action == "all_in":
        reasons.append("all-in")
    is_three_bet = action.street == "PREFLOP" and action.raised and preflop_raises == 1
    if three_bet or is_three_bet:
        reasons.append("3-bet pot")
    if action.street == "TURN":
        reasons.append("turn")
    if action.street == "RIVER":
        reasons.append("river")
    return reasons


def _score(action, by_seat, shared, street_put, active, big_blind, table, bounds) -> dict:
    player = by_seat[action.seat]
    board = _board_for(shared, action.street)
    bb = big_blind if big_blind else 1
    base = {
        "order": action.order_index,
        "street": action.street,
        "seat": action.seat,
        "position": player.position,
        "action": action.action,
        "amount": action.amount,
        "pot": action.pot_before,
        "acted_at": action.acted_at,
        "table": table,
        "player_count": len(active),
        "hero_cards": list(player.hole_cards or []),
        "assumption": _ASSUMPTION,
        "ev_loss_bb": None,
        "severity": None,
        "frequencies": {},
        "evs": {},
        "strategy": {},
        "matrix": [],
        "hero_matrix": [],
        "actions": [],
    }
    if action.street not in {"FLOP", "TURN", "RIVER"} or len(board) < 3:
        base["metadata"] = {
            "solver": "reference",
            "label": "unavailable",
            "exact": False,
            "available": False,
            "reason": "preflop",
        }
        return base
    hero_cards = list(player.hole_cards or [])
    if len(hero_cards) != 2:
        base["metadata"] = {
            "solver": "reference",
            "label": "unavailable",
            "exact": False,
            "available": False,
            "reason": "missing cards",
        }
        return base
    to_call = _to_call(action, street_put)
    if to_call > 0 and action.action in {"raise", "all_in"}:
        base["metadata"] = {
            "solver": "reference",
            "label": "Approximate Analysis" if len(active) >= 3 else "unavailable",
            "exact": False,
            "available": False,
            "reason": "raise is outside this one-decision tree",
        }
        return base
    sizes = _sizes(action, to_call)
    history = [{"action": "bet", "amount": to_call}] if to_call > 0 else []
    result = ReferenceSolverAdapter().solve_spot(
        SolveRequest(
            players=2,
            board=" ".join(board),
            pot=action.pot_before,
            effective_stack=max(int(action.stack_before), 1),
            hero_position=player.position,
            hero_range="".join(hero_cards),
            villain_range=VILLAIN_RANGE,
            action_history=history,
            bet_sizes=sizes,
            iterations=12,
            samples=4,
        )
    )
    metadata = dict(result.metadata)
    if len(active) >= 3:
        metadata["exact"] = False
        metadata["label"] = "Approximate Analysis"
        metadata["available"] = bool(result.frequencies)
    key = _hero_key(action, to_call)
    evs = dict(result.evs)
    loss = None
    severity = None
    if key in evs and evs:
        best = max(evs.values())
        loss = max(0.0, (best - evs[key]) / bb)
        severity = classify_loss(loss, **bounds)
    dead = set(parse_cards(" ".join([*board, *hero_cards])))
    villain = remove_blockers(parse_range(VILLAIN_RANGE), dead)
    base.update(
        {
            "actions": list(result.actions),
            "frequencies": dict(result.frequencies),
            "evs": evs,
            "strategy": result.strategy,
            "matrix": matrix(villain),
            "hero_matrix": matrix(parse_range("".join(hero_cards))),
            "hero_key": key,
            "ev_loss_bb": loss,
            "severity": severity,
            "metadata": metadata,
        }
    )
    return base


def _to_call(action, street_put: dict[int, int]) -> int:
    if action.action in {"check", "bet"}:
        return 0
    hero_in = street_put.get(action.seat, 0)
    current = max(street_put.values(), default=0)
    return max(0, current - hero_in)


def _sizes(action, to_call: int) -> list[int]:
    if to_call > 0:
        return []
    if action.action in {"bet", "raise", "all_in"} and action.put_in > 0:
        return [int(action.put_in)]
    half = max(1, int(action.pot_before) // 2)
    full = max(half, int(action.pot_before))
    if half == full:
        return [full]
    return [half, full]


def _hero_key(action, to_call: int) -> str | None:
    if to_call > 0:
        if action.action == "fold":
            return "fold"
        if action.action == "call":
            return "call"
        return None
    if action.action == "check":
        return "check"
    if action.action in {"bet", "raise", "all_in"} and action.put_in > 0:
        return f"bet:{int(action.put_in)}"
    return None


def _board_for(shared: list[str], street: str) -> list[str]:
    length = {"FLOP": 3, "TURN": 4, "RIVER": 5}.get(street, 0)
    return list(shared[:length])


def _table(action, shared, by_seat, stacks, active) -> dict:
    return {
        "street": action.street,
        "board": _board_for(shared, action.street),
        "pot": action.pot_before,
        "players": [
            {
                "seat": seat,
                "nickname": by_seat[seat].nickname,
                "position": by_seat[seat].position,
                "stack": stacks.get(seat, 0),
                "in_hand": seat in active,
            }
            for seat in sorted(by_seat)
        ],
    }


def _chain(nodes: list[dict]) -> dict:
    root: dict = {"kind": "hand", "children": []}
    cursor = root
    for node in nodes:
        child = {**node, "children": []}
        cursor["children"].append(child)
        cursor = child
    return root


def _persist(engine, hand_id: int, report: dict) -> None:
    now = datetime.now(UTC).isoformat()
    with Session(engine) as session:
        hand = session.get(Hand, hand_id)
        session.execute(delete(TrainerSpot).where(TrainerSpot.hand_id == hand_id))
        job = AnalysisJob(
            created_at=now,
            status="complete",
            adapter="reference",
            mode="posthand",
            exact=False,
            label="post-hand",
            room_id=None if hand is None else hand.room_id,
            hand_id=hand_id,
            request_json={"hand_id": hand_id},
            result_json={"decisions": len(report["decisions"])},
        )
        session.add(job)
        session.flush()
        for decision in report["decisions"]:
            if decision.get("ev_loss_bb") is None:
                continue
            session.add(
                DecisionAnalysis(
                    job_id=job.id,
                    hand_id=hand_id,
                    street=str(decision["street"]).lower(),
                    seat=decision["seat"],
                    position=decision["position"],
                    action=decision["action"],
                    ev=_chosen_ev(decision),
                    ev_loss=decision["ev_loss_bb"],
                    severity=decision["severity"],
                    payload={"reasons": decision["reasons"], "hero_key": decision.get("hero_key")},
                )
            )
            if decision["severity"] and decision["severity"] != "Good":
                session.add(_spot(now, hand, decision))
        session.commit()


def _chosen_ev(decision: dict) -> float | None:
    key = decision.get("hero_key")
    evs = decision.get("evs") or {}
    if key not in evs:
        return None
    return float(evs[key])


def _spot(now: str, hand: Hand | None, decision: dict) -> TrainerSpot:
    prompt = {
        "street": decision["street"],
        "position": decision["position"],
        "board": decision["table"]["board"],
        "pot": decision["pot"],
        "hero_cards": decision["hero_cards"],
        "actions": decision["actions"],
        "table": decision["table"],
        "assumption": decision["assumption"],
    }
    answer = {
        "frequencies": decision["frequencies"],
        "evs": decision["evs"],
        "strategy": decision["strategy"],
        "original_action": decision["action"],
        "original_key": decision.get("hero_key"),
        "ev_loss": decision["ev_loss_bb"],
        "severity": decision["severity"],
        "metadata": decision["metadata"],
        "matrix": decision["matrix"],
    }
    return TrainerSpot(
        created_at=now,
        decided_at=decision.get("acted_at"),
        hand_id=None if hand is None else hand.id,
        room_id=None if hand is None else hand.room_id,
        street=decision["street"],
        seat=decision["seat"],
        position=decision["position"],
        severity=decision["severity"],
        original_action=decision["action"],
        ev_loss=decision["ev_loss_bb"],
        spot_json={"prompt": prompt, "answer": answer},
    )


def _public_spot(row: TrainerSpot) -> dict:
    stored = dict(row.spot_json or {})
    prompt = dict(stored.get("prompt") or {})
    return {
        "id": row.id,
        "hand_id": row.hand_id,
        "street": row.street,
        "position": row.position,
        "severity": row.severity,
        "decided_at": row.decided_at,
        "created_at": row.created_at,
        "prompt": prompt,
    }
