"""Write a completed hand. Replay does not need the live room after this."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy import select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.database.models import (
    ActionRow,
    BoardRow,
    Hand,
    HandPlayer,
    Player,
    PotRow,
    RoomRow,
    RuleEvent,
)

if TYPE_CHECKING:
    from app.services.rooms import Room


def canonical_rules(value: dict | None) -> str:
    return json.dumps(value or {}, sort_keys=True, separators=(",", ":"))


class HandHistory:
    def __init__(self, engine: Engine) -> None:
        self.engine = engine
        self.sessions = sessionmaker(bind=engine, expire_on_commit=False)

    def save_room(self, room: Room) -> int:
        with self.sessions() as session:
            hand_id = insert_hand(session, room)
            session.commit()
            return hand_id


def insert_hand(session: Session, room: Room) -> int:
    game = room.game
    if game is None or not room.opening:
        raise RuntimeError("completed hand is missing its opening snapshot")
    completed_at = datetime.now(UTC).isoformat()
    room_row = session.get(RoomRow, room.room_id)
    if room_row is None:
        room_row = RoomRow(
            id=room.room_id,
            invite_code=room.invite_code,
            created_at=room.created_at,
            small_blind=room.small_blind,
            big_blind=room.big_blind,
            seat_count=room.seat_count,
        )
        session.add(room_row)
    else:
        room_row.small_blind = room.small_blind
        room_row.big_blind = room.big_blind
        room_row.seat_count = room.seat_count
    session.flush()

    player_ids: dict[str, int] = {}
    for row in room.opening:
        player_ids[row["nickname"]] = _player_id(session, row["nickname"], completed_at)

    button = room.engine_seats[game.button]
    showdown_seats = {room.engine_seats[seat] for seat in game.showdown_seats}
    payouts = _payouts(room)
    all_ins = _all_in_seats(room)
    winners = [row["seat"] for row in payouts if row["pot_payout"] > 0]
    hand = Hand(
        room_id=room.room_id,
        started_at=room.hand_started_at or completed_at,
        completed_at=completed_at,
        small_blind=game.small_blind,
        big_blind=game.big_blind,
        button_seat=button,
        sb_seat=_table(room, game.sb_seat),
        bb_seat=_table(room, game.bb_seat),
        opening_street=game.street_path[0].value if game.street_path else "PREFLOP",
        table_settings={
            "small_blind": game.small_blind,
            "big_blind": game.big_blind,
            "seats": room.seat_count,
            "button": button,
        },
        rule_settings=dict(room.rules_spec),
        rake=game.rake,
        bounty=game.bounty,
        showdown=bool(game.showdown_seats),
        all_in_seats=all_ins,
        winners=winners,
    )
    # street_path starts at POSTING_BLINDS or the first dealt street. Opening
    # street for replay is the first street a player can act on.
    acted = [item["street"] for item in room.hand_history]
    if acted:
        hand.opening_street = "PREFLOP" if "PREFLOP" in acted else acted[0]
    elif game.board:
        hand.opening_street = "FLOP"
    else:
        hand.opening_street = "PREFLOP"
    session.add(hand)
    session.flush()

    for row, paid in zip(room.opening, payouts, strict=True):
        session.add(
            HandPlayer(
                hand_id=hand.id,
                player_id=player_ids[row["nickname"]],
                seat=row["seat"],
                position=row["position"] or "",
                nickname=row["nickname"],
                is_bot=row["is_bot"],
                starting_stack=row["starting_stack"],
                posted=row["posted"],
                stack_after_posts=row["stack_after_posts"],
                ending_stack=paid["ending_stack"],
                hole_cards=list(row["hole_cards"]),
                pot_payout=paid["pot_payout"],
                bounty_payout=paid["bounty_payout"],
                showed=row["seat"] in showdown_seats,
            )
        )
    for index, item in enumerate(room.hand_history):
        session.add(
            ActionRow(
                hand_id=hand.id,
                order_index=index,
                street=item["street"],
                seat=item["seat"],
                player_id=player_ids.get(item["nickname"]),
                action=item["action"],
                amount=item["amount"],
                put_in=item["put_in"],
                pot_before=item["pot_before"],
                stack_before=item["stack_before"],
                raised=bool(item["raised"]),
                acted_at=item["acted_at"],
            )
        )
    for run_index, cards in enumerate(_runs(game)):
        session.add(
            BoardRow(
                hand_id=hand.id,
                run_index=run_index,
                flop=cards[:3],
                turn=cards[3] if len(cards) > 3 else None,
                river=cards[4] if len(cards) > 4 else None,
                cards=cards,
            )
        )
    for index, pot in enumerate(game.pots):
        session.add(
            PotRow(
                hand_id=hand.id,
                pot_index=index,
                amount=pot.amount,
                eligible=[_table(room, seat) for seat in pot.eligible],
                side_pot=index > 0,
            )
        )
    if game.rake:
        session.add(RuleEvent(hand_id=hand.id, kind="rake", payload={"amount": game.rake}))
    if game.bounty or game.bounty_payments:
        session.add(
            RuleEvent(
                hand_id=hand.id,
                kind="bounty",
                payload={"amount": game.bounty, "payments": _bounty_payload(room)},
            )
        )
    if game.rit_result is not None:
        session.add(
            RuleEvent(
                hand_id=hand.id,
                kind="run_it_twice",
                payload=_rit_payload(room, game.rit_result),
            )
        )
    if room.hand_top_ups:
        session.add(
            RuleEvent(hand_id=hand.id, kind="top_up", payload={"top_ups": list(room.hand_top_ups)})
        )
    session.flush()
    return hand.id


def _player_id(session: Session, nickname: str, created_at: str) -> int:
    found = session.scalar(select(Player).where(Player.nickname == nickname))
    if found is not None:
        return found.id
    player = Player(nickname=nickname, created_at=created_at)
    session.add(player)
    session.flush()
    return player.id


def _table(room: Room, engine_seat: int | None) -> int | None:
    if engine_seat is None:
        return None
    return room.engine_seats[engine_seat]


def _payouts(room: Room) -> list[dict]:
    game = room.game
    assert game is not None
    rows = []
    for opening in room.opening:
        engine_seat = opening["engine_seat"]
        player = game.players[engine_seat]
        bounty_in = sum(
            payment["amount"]
            for payment in game.bounty_payments
            if payment["winner"] == engine_seat
        )
        bounty_out = sum(
            payment["amount"]
            for payment in game.bounty_payments
            if payment["seat"] == engine_seat
        )
        net_bounty = bounty_in - bounty_out
        ending = player.stack
        pot_payout = ending - opening["starting_stack"] + player.committed_hand - net_bounty
        rows.append(
            {
                "seat": opening["seat"],
                "ending_stack": ending,
                "pot_payout": pot_payout,
                "bounty_payout": net_bounty,
            }
        )
    return rows


def _all_in_seats(room: Room) -> list[int]:
    seats: list[int] = []
    for item in room.hand_history:
        if item["action"] == "all_in" and item["seat"] not in seats:
            seats.append(item["seat"])
    for row in room.opening:
        if row["starting_stack"] > 0 and row["posted"] >= row["starting_stack"]:
            if row["seat"] not in seats:
                seats.append(row["seat"])
    return seats


def _runs(game: object) -> list[list[str]]:
    boards = getattr(game, "boards", None) or []
    if boards:
        return [[card.code for card in board] for board in boards]
    board = getattr(game, "board", None) or []
    if not board:
        return []
    return [[card.code for card in board]]


def _bounty_payload(room: Room) -> list[dict]:
    game = room.game
    assert game is not None
    return [
        {
            "seat": _table(room, payment["seat"]),
            "winner": _table(room, payment["winner"]),
            "amount": payment["amount"],
            "partial": payment["partial"],
        }
        for payment in game.bounty_payments
    ]


def _rit_payload(room: Room, result: dict) -> dict:
    runs = []
    for run in result.get("runs", []):
        pots = []
        for pot in run["pots"]:
            pots.append(
                {
                    "amount": pot["amount"],
                    "eligible": [_table(room, seat) for seat in pot["eligible"]],
                    "awards": [
                        {"seat": _table(room, award["seat"]), "amount": award["amount"]}
                        for award in pot["awards"]
                    ],
                }
            )
        runs.append({"board": list(run["board"]), "pots": pots})
    return {"accepted": bool(result.get("accepted", False)), "runs": runs}
