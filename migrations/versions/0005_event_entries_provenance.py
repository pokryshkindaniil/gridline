"""event entries: provenance + competition on vehicle_entries, kind on source_runs

Revision ID: 0005
Revises: 0004
Create Date: 2026-10-04 23:10:00.000000
"""
from alembic import op
import sqlalchemy as sa


revision = '0005'
down_revision = '0004'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('vehicle_entries', sa.Column('competition', sa.String(length=60), nullable=True))
    op.add_column('vehicle_entries', sa.Column('source_name', sa.String(length=200), nullable=True))
    op.add_column('vehicle_entries', sa.Column('source_url', sa.String(length=500), nullable=True))
    op.add_column('vehicle_entries', sa.Column('checked_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('source_runs', sa.Column('kind', sa.String(length=10), server_default='schedule', nullable=False))


def downgrade() -> None:
    op.drop_column('source_runs', 'kind')
    op.drop_column('vehicle_entries', 'checked_at')
    op.drop_column('vehicle_entries', 'source_url')
    op.drop_column('vehicle_entries', 'source_name')
    op.drop_column('vehicle_entries', 'competition')
