"""vacation days already taken, per person

The admin records in the profile how many vacation days a person has taken, so the
balance the worker sees (and the liquidation's default) subtracts them.

Revision ID: 0011
Revises: 0010
Create Date: 2026-09-28 22:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0011'
down_revision: Union[str, None] = '0010'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('users', sa.Column('vacation_days_taken', sa.Float(), server_default='0', nullable=False))


def downgrade() -> None:
    op.drop_column('users', 'vacation_days_taken')
