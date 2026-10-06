"""Columns for analysis jobs and decisions.

Revision ID: analysis_002
Revises: hand_history_001
"""

import sqlalchemy as sa
from alembic import op

revision = "analysis_002"
down_revision = "hand_history_001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("analysis_jobs", sa.Column("created_at", sa.String(40), nullable=True))
    op.add_column("analysis_jobs", sa.Column("status", sa.String(24), nullable=True))
    op.add_column("analysis_jobs", sa.Column("adapter", sa.String(24), nullable=True))
    op.add_column("analysis_jobs", sa.Column("mode", sa.String(24), nullable=True))
    op.add_column("analysis_jobs", sa.Column("exact", sa.Boolean(), nullable=True))
    op.add_column("analysis_jobs", sa.Column("label", sa.String(64), nullable=True))
    op.add_column("analysis_jobs", sa.Column("room_id", sa.String(32), nullable=True))
    op.add_column("analysis_jobs", sa.Column("hand_id", sa.Integer(), nullable=True))
    op.add_column("analysis_jobs", sa.Column("message", sa.String(240), nullable=True))
    op.add_column("analysis_jobs", sa.Column("request_json", sa.JSON(), nullable=True))
    op.add_column("analysis_jobs", sa.Column("result_json", sa.JSON(), nullable=True))
    op.add_column("decision_analysis", sa.Column("job_id", sa.Integer(), nullable=True))
    op.add_column("decision_analysis", sa.Column("hand_id", sa.Integer(), nullable=True))
    op.add_column("decision_analysis", sa.Column("street", sa.String(16), nullable=True))
    op.add_column("decision_analysis", sa.Column("seat", sa.Integer(), nullable=True))
    op.add_column("decision_analysis", sa.Column("position", sa.String(8), nullable=True))
    op.add_column("decision_analysis", sa.Column("action", sa.String(16), nullable=True))
    op.add_column("decision_analysis", sa.Column("ev", sa.Float(), nullable=True))
    op.add_column("decision_analysis", sa.Column("ev_loss", sa.Float(), nullable=True))
    op.add_column("decision_analysis", sa.Column("severity", sa.String(16), nullable=True))
    op.add_column("decision_analysis", sa.Column("payload", sa.JSON(), nullable=True))


def downgrade() -> None:
    for name in (
        "payload",
        "severity",
        "ev_loss",
        "ev",
        "action",
        "position",
        "seat",
        "street",
        "hand_id",
        "job_id",
    ):
        op.drop_column("decision_analysis", name)
    for name in (
        "result_json",
        "request_json",
        "message",
        "hand_id",
        "room_id",
        "label",
        "exact",
        "mode",
        "adapter",
        "status",
        "created_at",
    ):
        op.drop_column("analysis_jobs", name)
