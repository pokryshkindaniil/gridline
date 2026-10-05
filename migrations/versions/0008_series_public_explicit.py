"""make Series.public correct for every catalogue series

Revision ID: 0008
Revises: 0007
Create Date: 2026-10-05 16:00:00.000000
"""
from alembic import op


revision = '0008'
down_revision = '0007'
branch_labels = None
depends_on = None

PUBLIC = ('formula-1', 'fia-wec', 'gt-world-challenge-europe')
HIDDEN = ('imsa-weathertech', 'wrc', 'formula-e', 'motogp')


def upgrade() -> None:
    # WRC, Formula E and MotoGP defaulted to public=true although GRIDLINE has no source for them. No rows are deleted.
    op.execute("UPDATE series SET public = true WHERE slug IN (%s)" % ", ".join(f"'{s}'" for s in PUBLIC))
    op.execute("UPDATE series SET public = false WHERE slug IN (%s)" % ", ".join(f"'{s}'" for s in HIDDEN))


def downgrade() -> None:
    # Data correction: nothing to undo structurally. (The previous wrong state is deliberately not restored.)
    pass
