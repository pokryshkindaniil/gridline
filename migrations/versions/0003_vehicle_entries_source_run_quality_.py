"""vehicle entries, source run quality columns

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-04 20:58:54.853290
"""
from alembic import op
import sqlalchemy as sa


revision = '0003'
down_revision = '0002'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('vehicle_entries',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('team_id', sa.UUID(), nullable=False),
    sa.Column('season_id', sa.UUID(), nullable=False),
    sa.Column('event_id', sa.UUID(), nullable=True),
    sa.Column('race_number', sa.String(length=8), nullable=True),
    sa.Column('manufacturer', sa.String(length=120), nullable=True),
    sa.Column('model', sa.String(length=120), nullable=True),
    sa.Column('class_name', sa.String(length=60), nullable=True),
    sa.Column('image_url', sa.String(length=500), nullable=True),
    sa.Column('fallback_logo_url', sa.String(length=500), nullable=True),
    sa.ForeignKeyConstraint(['event_id'], ['events.id'], name=op.f('fk_vehicle_entries_event_id_events'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['season_id'], ['seasons.id'], name=op.f('fk_vehicle_entries_season_id_seasons'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['team_id'], ['teams.id'], name=op.f('fk_vehicle_entries_team_id_teams'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_vehicle_entries'))
    )
    op.create_index('ix_vehicle_entries_event_id', 'vehicle_entries', ['event_id'], unique=False)
    op.create_index('ix_vehicle_entries_season_id_team_id', 'vehicle_entries', ['season_id', 'team_id'], unique=False)
    op.create_index('uq_vehicle_entries_event_number', 'vehicle_entries', ['team_id', 'season_id', 'event_id', 'race_number'], unique=True, postgresql_where=sa.text('event_id IS NOT NULL'))
    op.create_index('uq_vehicle_entries_season_number', 'vehicle_entries', ['team_id', 'season_id', 'race_number'], unique=True, postgresql_where=sa.text('event_id IS NULL'))
    op.create_table('vehicle_entry_drivers',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('vehicle_entry_id', sa.UUID(), nullable=False),
    sa.Column('driver_id', sa.UUID(), nullable=False),
    sa.Column('position', sa.Integer(), server_default='0', nullable=False),
    sa.Column('role', sa.String(length=40), nullable=True),
    sa.ForeignKeyConstraint(['driver_id'], ['drivers.id'], name=op.f('fk_vehicle_entry_drivers_driver_id_drivers'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['vehicle_entry_id'], ['vehicle_entries.id'], name=op.f('fk_vehicle_entry_drivers_vehicle_entry_id_vehicle_entries'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_vehicle_entry_drivers')),
    sa.UniqueConstraint('vehicle_entry_id', 'driver_id', name=op.f('uq_vehicle_entry_drivers_vehicle_entry_id'))
    )
    op.create_index('ix_vehicle_entry_drivers_driver_id', 'vehicle_entry_drivers', ['driver_id'], unique=False)
    # --- data: vehicles + team_drivers -> vehicle_entries + vehicle_entry_drivers -----------------
    op.execute("""
        INSERT INTO vehicle_entries (id, team_id, season_id, race_number, manufacturer, model, class_name, image_url, fallback_logo_url)
        SELECT gen_random_uuid(), g.team_id, g.season_id, g.race_number, v.manufacturer, v.model, v.class_name, v.image_url, v.fallback_logo_url
        FROM (SELECT DISTINCT team_id, season_id, race_number FROM team_drivers) g
        LEFT JOIN LATERAL (
            SELECT * FROM vehicles x WHERE x.team_id = g.team_id AND x.season_id = g.season_id
            ORDER BY (x.race_number IS NOT DISTINCT FROM g.race_number) DESC, x.race_number LIMIT 1
        ) v ON true
    """)
    op.execute("""
        INSERT INTO vehicle_entries (id, team_id, season_id, race_number, manufacturer, model, class_name, image_url, fallback_logo_url)
        SELECT gen_random_uuid(), v.team_id, v.season_id, v.race_number, v.manufacturer, v.model, v.class_name, v.image_url, v.fallback_logo_url
        FROM vehicles v
        WHERE NOT EXISTS (SELECT 1 FROM vehicle_entries e WHERE e.team_id = v.team_id AND e.season_id = v.season_id
                          AND e.event_id IS NULL AND e.race_number IS NOT DISTINCT FROM v.race_number)
    """)
    op.execute("""
        INSERT INTO vehicle_entry_drivers (id, vehicle_entry_id, driver_id, position, role)
        SELECT gen_random_uuid(), e.id, td.driver_id, td.position, td.role
        FROM team_drivers td JOIN vehicle_entries e
          ON e.team_id = td.team_id AND e.season_id = td.season_id AND e.event_id IS NULL
         AND e.race_number IS NOT DISTINCT FROM td.race_number
    """)
    op.drop_index(op.f('ix_vehicles_team_id_season_id'), table_name='vehicles')
    op.drop_table('vehicles')
    op.drop_index(op.f('ix_team_drivers_season_id_team_id'), table_name='team_drivers')
    op.drop_table('team_drivers')
    op.drop_constraint(op.f('fk_session_changes_session_id_sessions'), 'session_changes', type_='foreignkey')
    op.create_foreign_key(op.f('fk_session_changes_session_id_sessions'), 'session_changes', 'sessions', ['session_id'], ['id'], ondelete='RESTRICT')
    op.add_column('source_runs', sa.Column('issues', sa.Integer(), server_default='0', nullable=False))
    op.add_column('source_runs', sa.Column('duration_ms', sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column('source_runs', 'duration_ms')
    op.drop_column('source_runs', 'issues')
    op.drop_constraint(op.f('fk_session_changes_session_id_sessions'), 'session_changes', type_='foreignkey')
    op.create_foreign_key(op.f('fk_session_changes_session_id_sessions'), 'session_changes', 'sessions', ['session_id'], ['id'], ondelete='CASCADE')
    op.create_table('team_drivers',
    sa.Column('id', sa.UUID(), autoincrement=False, nullable=False),
    sa.Column('team_id', sa.UUID(), autoincrement=False, nullable=False),
    sa.Column('driver_id', sa.UUID(), autoincrement=False, nullable=False),
    sa.Column('season_id', sa.UUID(), autoincrement=False, nullable=False),
    sa.Column('race_number', sa.VARCHAR(length=8), autoincrement=False, nullable=True),
    sa.Column('role', sa.VARCHAR(length=40), autoincrement=False, nullable=True),
    sa.Column('valid_from', sa.DATE(), autoincrement=False, nullable=True),
    sa.Column('valid_to', sa.DATE(), autoincrement=False, nullable=True),
    sa.Column('position', sa.INTEGER(), server_default=sa.text('0'), autoincrement=False, nullable=False),
    sa.ForeignKeyConstraint(['driver_id'], ['drivers.id'], name=op.f('fk_team_drivers_driver_id_drivers'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['season_id'], ['seasons.id'], name=op.f('fk_team_drivers_season_id_seasons'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['team_id'], ['teams.id'], name=op.f('fk_team_drivers_team_id_teams'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_team_drivers')),
    sa.UniqueConstraint('team_id', 'driver_id', 'season_id', name=op.f('uq_team_drivers_team_id'), postgresql_include=[], postgresql_nulls_not_distinct=False)
    )
    op.create_index(op.f('ix_team_drivers_season_id_team_id'), 'team_drivers', ['season_id', 'team_id'], unique=False)
    op.create_table('vehicles',
    sa.Column('id', sa.UUID(), autoincrement=False, nullable=False),
    sa.Column('team_id', sa.UUID(), autoincrement=False, nullable=False),
    sa.Column('season_id', sa.UUID(), autoincrement=False, nullable=False),
    sa.Column('manufacturer', sa.VARCHAR(length=120), autoincrement=False, nullable=True),
    sa.Column('model', sa.VARCHAR(length=120), autoincrement=False, nullable=True),
    sa.Column('class_name', sa.VARCHAR(length=60), autoincrement=False, nullable=True),
    sa.Column('race_number', sa.VARCHAR(length=8), autoincrement=False, nullable=True),
    sa.Column('image_url', sa.VARCHAR(length=500), autoincrement=False, nullable=True),
    sa.Column('fallback_logo_url', sa.VARCHAR(length=500), autoincrement=False, nullable=True),
    sa.ForeignKeyConstraint(['season_id'], ['seasons.id'], name=op.f('fk_vehicles_season_id_seasons'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['team_id'], ['teams.id'], name=op.f('fk_vehicles_team_id_teams'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_vehicles'))
    )
    op.create_index(op.f('ix_vehicles_team_id_season_id'), 'vehicles', ['team_id', 'season_id'], unique=False)
    # --- data back-conversion (event-specific entries are dropped: the old model cannot express them) ---
    op.execute("""
        INSERT INTO vehicles (id, team_id, season_id, manufacturer, model, class_name, race_number, image_url, fallback_logo_url)
        SELECT id, team_id, season_id, manufacturer, model, class_name, race_number, image_url, fallback_logo_url
        FROM vehicle_entries WHERE event_id IS NULL
    """)
    op.execute("""
        INSERT INTO team_drivers (id, team_id, driver_id, season_id, race_number, role, position)
        SELECT gen_random_uuid(), e.team_id, d.driver_id, e.season_id, e.race_number, d.role, d.position
        FROM vehicle_entry_drivers d JOIN vehicle_entries e ON e.id = d.vehicle_entry_id WHERE e.event_id IS NULL
    """)
    op.drop_index('ix_vehicle_entry_drivers_driver_id', table_name='vehicle_entry_drivers')
    op.drop_table('vehicle_entry_drivers')
    op.drop_index('uq_vehicle_entries_season_number', table_name='vehicle_entries', postgresql_where=sa.text('event_id IS NULL'))
    op.drop_index('uq_vehicle_entries_event_number', table_name='vehicle_entries', postgresql_where=sa.text('event_id IS NOT NULL'))
    op.drop_index('ix_vehicle_entries_season_id_team_id', table_name='vehicle_entries')
    op.drop_index('ix_vehicle_entries_event_id', table_name='vehicle_entries')
    op.drop_table('vehicle_entries')
