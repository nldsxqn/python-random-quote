"""Poker tables. Statistics and trainer spots stay empty until their phase."""

from sqlalchemy import JSON, Boolean, Float, ForeignKey, Integer, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Player(Base):
    __tablename__ = "players"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    nickname: Mapped[str] = mapped_column(String(24), unique=True)
    created_at: Mapped[str] = mapped_column(String(40))


class RoomRow(Base):
    __tablename__ = "rooms"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    invite_code: Mapped[str] = mapped_column(String(16))
    created_at: Mapped[str] = mapped_column(String(40))
    small_blind: Mapped[int] = mapped_column(Integer)
    big_blind: Mapped[int] = mapped_column(Integer)
    seat_count: Mapped[int] = mapped_column(Integer)


class Hand(Base):
    __tablename__ = "hands"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    room_id: Mapped[str] = mapped_column(ForeignKey("rooms.id"), index=True)
    started_at: Mapped[str] = mapped_column(String(40))
    completed_at: Mapped[str] = mapped_column(String(40), index=True)
    small_blind: Mapped[int] = mapped_column(Integer)
    big_blind: Mapped[int] = mapped_column(Integer)
    button_seat: Mapped[int] = mapped_column(Integer)
    sb_seat: Mapped[int | None] = mapped_column(Integer, nullable=True)
    bb_seat: Mapped[int | None] = mapped_column(Integer, nullable=True)
    opening_street: Mapped[str] = mapped_column(String(16))
    table_settings: Mapped[dict] = mapped_column(JSON)
    rule_settings: Mapped[dict] = mapped_column(JSON)
    rake: Mapped[int] = mapped_column(Integer)
    bounty: Mapped[int] = mapped_column(Integer)
    showdown: Mapped[bool] = mapped_column(Boolean)
    all_in_seats: Mapped[list] = mapped_column(JSON)
    winners: Mapped[list] = mapped_column(JSON)


class HandPlayer(Base):
    __tablename__ = "hand_players"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    hand_id: Mapped[int] = mapped_column(ForeignKey("hands.id"), index=True)
    player_id: Mapped[int] = mapped_column(ForeignKey("players.id"), index=True)
    seat: Mapped[int] = mapped_column(Integer)
    position: Mapped[str] = mapped_column(String(8))
    nickname: Mapped[str] = mapped_column(String(24))
    is_bot: Mapped[bool] = mapped_column(Boolean)
    starting_stack: Mapped[int] = mapped_column(Integer)
    posted: Mapped[int] = mapped_column(Integer)
    stack_after_posts: Mapped[int] = mapped_column(Integer)
    ending_stack: Mapped[int] = mapped_column(Integer)
    hole_cards: Mapped[list] = mapped_column(JSON)
    pot_payout: Mapped[int] = mapped_column(Integer)
    bounty_payout: Mapped[int] = mapped_column(Integer)
    showed: Mapped[bool] = mapped_column(Boolean)


class ActionRow(Base):
    __tablename__ = "actions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    hand_id: Mapped[int] = mapped_column(ForeignKey("hands.id"), index=True)
    order_index: Mapped[int] = mapped_column(Integer)
    street: Mapped[str] = mapped_column(String(16))
    seat: Mapped[int] = mapped_column(Integer)
    player_id: Mapped[int | None] = mapped_column(ForeignKey("players.id"), nullable=True)
    action: Mapped[str] = mapped_column(String(16))
    amount: Mapped[int | None] = mapped_column(Integer, nullable=True)
    put_in: Mapped[int] = mapped_column(Integer)
    pot_before: Mapped[int] = mapped_column(Integer)
    stack_before: Mapped[int] = mapped_column(Integer)
    raised: Mapped[bool] = mapped_column(Boolean)
    acted_at: Mapped[str] = mapped_column(String(40))


class BoardRow(Base):
    __tablename__ = "boards"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    hand_id: Mapped[int] = mapped_column(ForeignKey("hands.id"), index=True)
    run_index: Mapped[int] = mapped_column(Integer)
    flop: Mapped[list] = mapped_column(JSON)
    turn: Mapped[str | None] = mapped_column(String(8), nullable=True)
    river: Mapped[str | None] = mapped_column(String(8), nullable=True)
    cards: Mapped[list] = mapped_column(JSON)


class PotRow(Base):
    __tablename__ = "pots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    hand_id: Mapped[int] = mapped_column(ForeignKey("hands.id"), index=True)
    pot_index: Mapped[int] = mapped_column(Integer)
    amount: Mapped[int] = mapped_column(Integer)
    eligible: Mapped[list] = mapped_column(JSON)
    side_pot: Mapped[bool] = mapped_column(Boolean)


class RuleEvent(Base):
    __tablename__ = "rule_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    hand_id: Mapped[int] = mapped_column(ForeignKey("hands.id"), index=True)
    kind: Mapped[str] = mapped_column(String(32))
    payload: Mapped[dict] = mapped_column(JSON)


class AnalysisJob(Base):
    __tablename__ = "analysis_jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    created_at: Mapped[str | None] = mapped_column(String(40), nullable=True)
    status: Mapped[str | None] = mapped_column(String(24), nullable=True)
    adapter: Mapped[str | None] = mapped_column(String(24), nullable=True)
    mode: Mapped[str | None] = mapped_column(String(24), nullable=True)
    exact: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    label: Mapped[str | None] = mapped_column(String(64), nullable=True)
    room_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    hand_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    message: Mapped[str | None] = mapped_column(String(240), nullable=True)
    request_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    result_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)


class DecisionAnalysis(Base):
    __tablename__ = "decision_analysis"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    job_id: Mapped[int | None] = mapped_column(ForeignKey("analysis_jobs.id"), nullable=True)
    hand_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    street: Mapped[str | None] = mapped_column(String(16), nullable=True)
    seat: Mapped[int | None] = mapped_column(Integer, nullable=True)
    position: Mapped[str | None] = mapped_column(String(8), nullable=True)
    action: Mapped[str | None] = mapped_column(String(16), nullable=True)
    ev: Mapped[float | None] = mapped_column(Float, nullable=True)
    ev_loss: Mapped[float | None] = mapped_column(Float, nullable=True)
    severity: Mapped[str | None] = mapped_column(String(16), nullable=True)
    payload: Mapped[dict | None] = mapped_column(JSON, nullable=True)


class PlayerStatistics(Base):
    __tablename__ = "player_statistics"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)


class TrainerSpot(Base):
    __tablename__ = "trainer_spots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    created_at: Mapped[str | None] = mapped_column(String(40), nullable=True)
    decided_at: Mapped[str | None] = mapped_column(String(40), nullable=True)
    hand_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    room_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    street: Mapped[str | None] = mapped_column(String(16), nullable=True)
    seat: Mapped[int | None] = mapped_column(Integer, nullable=True)
    position: Mapped[str | None] = mapped_column(String(8), nullable=True)
    severity: Mapped[str | None] = mapped_column(String(16), nullable=True)
    original_action: Mapped[str | None] = mapped_column(String(16), nullable=True)
    ev_loss: Mapped[float | None] = mapped_column(Float, nullable=True)
    spot_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
