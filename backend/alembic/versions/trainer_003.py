"""Trainer spot columns.

Revision ID: trainer_003
Revises: analysis_002
"""

import sqlalchemy as sa
from alembic import op

revision = "trainer_003"
down_revision = "analysis_002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("trainer_spots", sa.Column("created_at", sa.String(40), nullable=True))
    op.add_column("trainer_spots", sa.Column("decided_at", sa.String(40), nullable=True))
    op.add_column("trainer_spots", sa.Column("hand_id", sa.Integer(), nullable=True))
    op.add_column("trainer_spots", sa.Column("room_id", sa.String(32), nullable=True))
    op.add_column("trainer_spots", sa.Column("street", sa.String(16), nullable=True))
    op.add_column("trainer_spots", sa.Column("seat", sa.Integer(), nullable=True))
    op.add_column("trainer_spots", sa.Column("position", sa.String(8), nullable=True))
    op.add_column("trainer_spots", sa.Column("severity", sa.String(16), nullable=True))
    op.add_column("trainer_spots", sa.Column("original_action", sa.String(16), nullable=True))
    op.add_column("trainer_spots", sa.Column("ev_loss", sa.Float(), nullable=True))
    op.add_column("trainer_spots", sa.Column("spot_json", sa.JSON(), nullable=True))


def downgrade() -> None:
    for name in (
        "spot_json",
        "ev_loss",
        "original_action",
        "severity",
        "position",
        "seat",
        "street",
        "room_id",
        "hand_id",
        "decided_at",
        "created_at",
    ):
        op.drop_column("trainer_spots", name)
