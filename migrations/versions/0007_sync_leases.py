"""sync leases

Revision ID: 0007
Revises: 0006
Create Date: 2026-10-05 14:29:21.294754
"""
from alembic import op
import sqlalchemy as sa


revision = '0007'
down_revision = '0006'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('sync_leases',
    sa.Column('name', sa.String(length=80), nullable=False),
    sa.Column('owner_token', sa.String(length=64), nullable=False),
    sa.Column('acquired_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('heartbeat_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('name', name=op.f('pk_sync_leases'))
    )


def downgrade() -> None:
    op.drop_table('sync_leases')
