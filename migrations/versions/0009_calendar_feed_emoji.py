"""add optional emoji titles to calendar feeds

Revision ID: 0009
Revises: 0008
Create Date: 2026-10-06 09:30:00.000000
"""
import sqlalchemy as sa
from alembic import op


revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "calendar_feeds",
        sa.Column("include_emoji", sa.Boolean(), server_default="false", nullable=False),
    )


def downgrade() -> None:
    op.drop_column("calendar_feeds", "include_emoji")
