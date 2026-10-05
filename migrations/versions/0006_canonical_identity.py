"""canonical identity, vehicle models, series visibility

Revision ID: 0006
Revises: 0005
Create Date: 2026-10-05 00:16:34.888002
"""
from alembic import op
import sqlalchemy as sa


revision = '0006'
down_revision = '0005'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('manufacturers',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('slug', sa.String(length=120), nullable=False),
    sa.Column('canonical_name', sa.String(length=120), nullable=False),
    sa.Column('logo_url', sa.String(length=500), nullable=True),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_manufacturers')),
    sa.UniqueConstraint('slug', name=op.f('uq_manufacturers_slug'))
    )
    op.create_table('driver_aliases',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('driver_id', sa.UUID(), nullable=False),
    sa.Column('source_external_id', sa.String(length=120), nullable=True),
    sa.Column('source_name', sa.String(length=60), nullable=False),
    sa.Column('source_value', sa.String(length=300), nullable=False),
    sa.Column('normalized_value', sa.String(length=300), nullable=False),
    sa.Column('first_seen_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['driver_id'], ['drivers.id'], name=op.f('fk_driver_aliases_driver_id_drivers'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_driver_aliases')),
    sa.UniqueConstraint('source_name', 'normalized_value', name='uq_driver_aliases_source_value')
    )
    op.create_index('ix_driver_aliases_driver_id', 'driver_aliases', ['driver_id'], unique=False)
    op.create_index('ix_driver_aliases_source_external_id', 'driver_aliases', ['source_name', 'source_external_id'], unique=False)
    op.create_table('manufacturer_aliases',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('manufacturer_id', sa.UUID(), nullable=False),
    sa.Column('source_name', sa.String(length=60), nullable=False),
    sa.Column('source_value', sa.String(length=300), nullable=False),
    sa.Column('normalized_value', sa.String(length=300), nullable=False),
    sa.Column('first_seen_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['manufacturer_id'], ['manufacturers.id'], name=op.f('fk_manufacturer_aliases_manufacturer_id_manufacturers'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_manufacturer_aliases')),
    sa.UniqueConstraint('source_name', 'normalized_value', name='uq_manufacturer_aliases_source_value')
    )
    op.create_table('vehicle_models',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('manufacturer_id', sa.UUID(), nullable=False),
    sa.Column('slug', sa.String(length=120), nullable=False),
    sa.Column('canonical_name', sa.String(length=120), nullable=False),
    sa.Column('season_year', sa.Integer(), nullable=True),
    sa.Column('category', sa.String(length=60), nullable=True),
    sa.Column('source_name', sa.String(length=200), nullable=True),
    sa.Column('source_url', sa.String(length=500), nullable=True),
    sa.Column('checked_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['manufacturer_id'], ['manufacturers.id'], name=op.f('fk_vehicle_models_manufacturer_id_manufacturers'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_vehicle_models')),
    sa.UniqueConstraint('manufacturer_id', 'slug', name=op.f('uq_vehicle_models_manufacturer_id'))
    )
    op.create_table('team_aliases',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('team_id', sa.UUID(), nullable=False),
    sa.Column('source_external_id', sa.String(length=120), nullable=True),
    sa.Column('source_name', sa.String(length=60), nullable=False),
    sa.Column('source_value', sa.String(length=300), nullable=False),
    sa.Column('normalized_value', sa.String(length=300), nullable=False),
    sa.Column('first_seen_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['team_id'], ['teams.id'], name=op.f('fk_team_aliases_team_id_teams'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_team_aliases')),
    sa.UniqueConstraint('source_name', 'normalized_value', name='uq_team_aliases_source_value')
    )
    op.create_index('ix_team_aliases_team_id', 'team_aliases', ['team_id'], unique=False)
    op.add_column('drivers', sa.Column('birth_date', sa.Date(), nullable=True))
    op.add_column('series', sa.Column('public', sa.Boolean(), server_default='true', nullable=False))
    op.add_column('vehicle_entries', sa.Column('manufacturer_id', sa.UUID(), nullable=True))
    op.add_column('vehicle_entries', sa.Column('vehicle_model_id', sa.UUID(), nullable=True))
    op.create_foreign_key(op.f('fk_vehicle_entries_vehicle_model_id_vehicle_models'), 'vehicle_entries', 'vehicle_models', ['vehicle_model_id'], ['id'], ondelete='SET NULL')
    op.create_foreign_key(op.f('fk_vehicle_entries_manufacturer_id_manufacturers'), 'vehicle_entries', 'manufacturers', ['manufacturer_id'], ['id'], ondelete='SET NULL')
    # IMSA keeps its adapter, fixtures and data but is not part of the public product (no ingestible source yet).
    # app.catalog re-asserts Series.public on every sync/seed; this makes it true right after the upgrade.
    op.execute("UPDATE series SET public = false WHERE slug = 'imsa-weathertech'")


def downgrade() -> None:
    op.drop_constraint(op.f('fk_vehicle_entries_manufacturer_id_manufacturers'), 'vehicle_entries', type_='foreignkey')
    op.drop_constraint(op.f('fk_vehicle_entries_vehicle_model_id_vehicle_models'), 'vehicle_entries', type_='foreignkey')
    op.drop_column('vehicle_entries', 'vehicle_model_id')
    op.drop_column('vehicle_entries', 'manufacturer_id')
    op.drop_column('series', 'public')
    op.drop_column('drivers', 'birth_date')
    op.drop_index('ix_team_aliases_team_id', table_name='team_aliases')
    op.drop_table('team_aliases')
    op.drop_table('vehicle_models')
    op.drop_table('manufacturer_aliases')
    op.drop_index('ix_driver_aliases_source_external_id', table_name='driver_aliases')
    op.drop_index('ix_driver_aliases_driver_id', table_name='driver_aliases')
    op.drop_table('driver_aliases')
    op.drop_table('manufacturers')
