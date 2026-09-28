"""liquidation per Código de Trabajo

The liquidation now records why the contract ended, whether notice was given,
vacation days already taken, preaviso, cesantía and the worker CCSS withheld
(app/utils/liquidacion.py). Existing liquidations keep their amounts; the new
columns default to 0 / empty.

Revision ID: 0009
Revises: 0008
Create Date: 2026-09-28 08:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0009'
down_revision: Union[str, None] = '0008'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('liquidations', sa.Column('reason', sa.String(length=40), nullable=True))
    op.add_column('liquidations', sa.Column('notice_given', sa.Boolean(), server_default='false', nullable=False))
    op.add_column('liquidations', sa.Column('vacation_days_taken', sa.Float(), server_default='0', nullable=False))
    op.add_column('liquidations', sa.Column('preaviso_amount', sa.Float(), server_default='0', nullable=False))
    op.add_column('liquidations', sa.Column('cesantia_amount', sa.Float(), server_default='0', nullable=False))
    op.add_column('liquidations', sa.Column('ccss_deduction', sa.Float(), server_default='0', nullable=False))


def downgrade() -> None:
    for column in ('ccss_deduction', 'cesantia_amount', 'preaviso_amount', 'vacation_days_taken', 'notice_given',
                   'reason'):
        op.drop_column('liquidations', column)
