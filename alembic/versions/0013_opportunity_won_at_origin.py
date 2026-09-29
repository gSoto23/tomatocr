"""when an opportunity was won, and where it came from

won_at: the money goals count what was won inside the period (a tender takes months).
origin: web, referido, prospeccion, sicop, cliente_actual, otro; the Filtro filters by it.
Existing rows are filled from what the system already knows.

Revision ID: 0013
Revises: 0012
Create Date: 2026-09-29 18:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0013'
down_revision: Union[str, None] = '0012'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('opportunities', sa.Column('won_at', sa.DateTime(), nullable=True))
    op.add_column('opportunities', sa.Column('origin', sa.String(length=30), nullable=True))
    # Won: the last stage change to "Ganado", or the last update if there is none.
    op.execute("""
        UPDATE opportunities SET won_at = COALESCE(
            (SELECT MAX(a.happened_at) FROM crm_activities a
              WHERE a.opportunity_id = opportunities.id AND a.type = 'cambio_etapa' AND a.notes LIKE '%→ Ganado%'),
            updated_at, created_at)
        WHERE stage = 'ganado'
    """)
    # Origin, most specific first.
    op.execute("UPDATE opportunities SET origin = 'web' WHERE source IN ('web', 'darboles', 'google')")
    op.execute("UPDATE opportunities SET origin = 'referido' WHERE source = 'referido'")
    op.execute("UPDATE opportunities SET origin = 'sicop' WHERE source = 'sicop'")
    op.execute("UPDATE opportunities SET origin = 'prospeccion' "
               "WHERE source IN ('linkedin', 'correo', 'whatsapp', 'evento', 'visita')")
    op.execute("UPDATE opportunities SET origin = 'cliente_actual' "
               "WHERE origin IS NULL AND (kind IN ('renovacion', 'ampliacion') OR source = 'renovacion')")
    op.execute("UPDATE opportunities SET origin = 'sicop' WHERE origin IS NULL AND motor = 'sector_publico'")


def downgrade() -> None:
    op.drop_column('opportunities', 'origin')
    op.drop_column('opportunities', 'won_at')
