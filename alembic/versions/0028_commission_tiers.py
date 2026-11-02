"""comisiones: umbral por monto de factura con dos porcentajes (reglas propias por persona)

Revision ID: 0028
Revises: 0027
Create Date: 2026-11-02 18:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0028'
down_revision: Union[str, None] = '0027'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('users', sa.Column('commission_threshold', sa.Float(), nullable=True))
    op.add_column('users', sa.Column('commission_percent_high', sa.Float(), nullable=True))


def downgrade() -> None:
    op.drop_column('users', 'commission_percent_high')
    op.drop_column('users', 'commission_threshold')
