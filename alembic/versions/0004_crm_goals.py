"""crm goals

Fase 2B: funnel targets per stage, seeded with the pilot targets
(prospecto 150, respuesta 60, reunion 25, propuesta 10, ganado 4).

Revision ID: 0004
Revises: 0003
Create Date: 2026-09-27 10:11:59.316268

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0004'
down_revision: Union[str, None] = '0003'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('crm_goals',
    sa.Column('stage', sa.String(length=20), nullable=False),
    sa.Column('target', sa.Integer(), nullable=False),
    sa.PrimaryKeyConstraint('stage')
    )
    goals = sa.table('crm_goals', sa.column('stage', sa.String), sa.column('target', sa.Integer))
    op.bulk_insert(goals, [
        {'stage': 'prospecto', 'target': 150},
        {'stage': 'respuesta', 'target': 60},
        {'stage': 'reunion', 'target': 25},
        {'stage': 'propuesta', 'target': 10},
        {'stage': 'ganado', 'target': 4},
    ])


def downgrade() -> None:
    op.drop_table('crm_goals')
