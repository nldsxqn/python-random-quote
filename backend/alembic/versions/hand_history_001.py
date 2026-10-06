"""Hand history, replay, and reserved analysis tables.

Revision ID: hand_history_001
Revises:
Create Date: 2026-10-05
"""

import sqlalchemy as sa
from alembic import op

revision = "hand_history_001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "players",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("nickname", sa.String(24), nullable=False),
        sa.Column("created_at", sa.String(40), nullable=False),
        sa.UniqueConstraint("nickname"),
    )
    op.create_table(
        "rooms",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("invite_code", sa.String(16), nullable=False),
        sa.Column("created_at", sa.String(40), nullable=False),
        sa.Column("small_blind", sa.Integer(), nullable=False),
        sa.Column("big_blind", sa.Integer(), nullable=False),
        sa.Column("seat_count", sa.Integer(), nullable=False),
    )
    op.create_table(
        "hands",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("room_id", sa.String(32), sa.ForeignKey("rooms.id"), nullable=False),
        sa.Column("started_at", sa.String(40), nullable=False),
        sa.Column("completed_at", sa.String(40), nullable=False),
        sa.Column("small_blind", sa.Integer(), nullable=False),
        sa.Column("big_blind", sa.Integer(), nullable=False),
        sa.Column("button_seat", sa.Integer(), nullable=False),
        sa.Column("sb_seat", sa.Integer(), nullable=True),
        sa.Column("bb_seat", sa.Integer(), nullable=True),
        sa.Column("opening_street", sa.String(16), nullable=False),
        sa.Column("table_settings", sa.JSON(), nullable=False),
        sa.Column("rule_settings", sa.JSON(), nullable=False),
        sa.Column("rake", sa.Integer(), nullable=False),
        sa.Column("bounty", sa.Integer(), nullable=False),
        sa.Column("showdown", sa.Boolean(), nullable=False),
        sa.Column("all_in_seats", sa.JSON(), nullable=False),
        sa.Column("winners", sa.JSON(), nullable=False),
    )
    op.create_index("ix_hands_room_id", "hands", ["room_id"])
    op.create_index("ix_hands_completed_at", "hands", ["completed_at"])
    op.create_table(
        "hand_players",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("hand_id", sa.Integer(), sa.ForeignKey("hands.id"), nullable=False),
        sa.Column("player_id", sa.Integer(), sa.ForeignKey("players.id"), nullable=False),
        sa.Column("seat", sa.Integer(), nullable=False),
        sa.Column("position", sa.String(8), nullable=False),
        sa.Column("nickname", sa.String(24), nullable=False),
        sa.Column("is_bot", sa.Boolean(), nullable=False),
        sa.Column("starting_stack", sa.Integer(), nullable=False),
        sa.Column("posted", sa.Integer(), nullable=False),
        sa.Column("stack_after_posts", sa.Integer(), nullable=False),
        sa.Column("ending_stack", sa.Integer(), nullable=False),
        sa.Column("hole_cards", sa.JSON(), nullable=False),
        sa.Column("pot_payout", sa.Integer(), nullable=False),
        sa.Column("bounty_payout", sa.Integer(), nullable=False),
        sa.Column("showed", sa.Boolean(), nullable=False),
    )
    op.create_index("ix_hand_players_hand_id", "hand_players", ["hand_id"])
    op.create_index("ix_hand_players_player_id", "hand_players", ["player_id"])
    op.create_table(
        "actions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("hand_id", sa.Integer(), sa.ForeignKey("hands.id"), nullable=False),
        sa.Column("order_index", sa.Integer(), nullable=False),
        sa.Column("street", sa.String(16), nullable=False),
        sa.Column("seat", sa.Integer(), nullable=False),
        sa.Column("player_id", sa.Integer(), sa.ForeignKey("players.id"), nullable=True),
        sa.Column("action", sa.String(16), nullable=False),
        sa.Column("amount", sa.Integer(), nullable=True),
        sa.Column("put_in", sa.Integer(), nullable=False),
        sa.Column("pot_before", sa.Integer(), nullable=False),
        sa.Column("stack_before", sa.Integer(), nullable=False),
        sa.Column("raised", sa.Boolean(), nullable=False),
        sa.Column("acted_at", sa.String(40), nullable=False),
    )
    op.create_index("ix_actions_hand_id", "actions", ["hand_id"])
    op.create_table(
        "boards",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("hand_id", sa.Integer(), sa.ForeignKey("hands.id"), nullable=False),
        sa.Column("run_index", sa.Integer(), nullable=False),
        sa.Column("flop", sa.JSON(), nullable=False),
        sa.Column("turn", sa.String(8), nullable=True),
        sa.Column("river", sa.String(8), nullable=True),
        sa.Column("cards", sa.JSON(), nullable=False),
    )
    op.create_index("ix_boards_hand_id", "boards", ["hand_id"])
    op.create_table(
        "pots",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("hand_id", sa.Integer(), sa.ForeignKey("hands.id"), nullable=False),
        sa.Column("pot_index", sa.Integer(), nullable=False),
        sa.Column("amount", sa.Integer(), nullable=False),
        sa.Column("eligible", sa.JSON(), nullable=False),
        sa.Column("side_pot", sa.Boolean(), nullable=False),
    )
    op.create_index("ix_pots_hand_id", "pots", ["hand_id"])
    op.create_table(
        "rule_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("hand_id", sa.Integer(), sa.ForeignKey("hands.id"), nullable=False),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
    )
    op.create_index("ix_rule_events_hand_id", "rule_events", ["hand_id"])
    op.create_table("analysis_jobs", sa.Column("id", sa.Integer(), primary_key=True))
    op.create_table("decision_analysis", sa.Column("id", sa.Integer(), primary_key=True))
    op.create_table("player_statistics", sa.Column("id", sa.Integer(), primary_key=True))
    op.create_table("trainer_spots", sa.Column("id", sa.Integer(), primary_key=True))


def downgrade() -> None:
    op.drop_table("trainer_spots")
    op.drop_table("player_statistics")
    op.drop_table("decision_analysis")
    op.drop_table("analysis_jobs")
    op.drop_table("rule_events")
    op.drop_table("pots")
    op.drop_table("boards")
    op.drop_table("actions")
    op.drop_table("hand_players")
    op.drop_table("hands")
    op.drop_table("rooms")
    op.drop_table("players")
