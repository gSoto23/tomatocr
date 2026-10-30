"""calendario: attendance of each assignment (asistió, llegó tarde, no llegó)

Revision ID: 0022
Revises: 0021
Create Date: 2026-10-30 10:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0022'
down_revision: Union[str, None] = '0021'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('project_schedules', sa.Column('attendance', sa.String(length=12), nullable=True))


def downgrade() -> None:
    op.drop_column('project_schedules', 'attendance')
