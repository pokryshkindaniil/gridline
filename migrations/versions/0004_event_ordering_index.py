"""event ordering index

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-04 21:04:53.692619
"""
from alembic import op
import sqlalchemy as sa


revision = '0004'
down_revision = '0003'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index('ix_events_season_id_start_date', 'events', ['season_id', 'start_date'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_events_season_id_start_date', table_name='events')
