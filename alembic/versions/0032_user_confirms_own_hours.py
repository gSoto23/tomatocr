"""a supervisor who confirms their own hours (an exception the admin sets in Empleados)

Revision ID: 0032
Revises: 0031
Create Date: 2026-11-23 10:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0032'
down_revision: Union[str, None] = '0031'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('users', sa.Column('confirms_own_hours', sa.Boolean(), server_default=sa.text('false'),
                                     nullable=False))


def downgrade() -> None:
    op.drop_column('users', 'confirms_own_hours')
