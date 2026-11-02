"""planilla: una quincena aprobada se puede marcar como pagada fuera del sistema

Revision ID: 0027
Revises: 0026
Create Date: 2026-11-02 16:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0027'
down_revision: Union[str, None] = '0026'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('payroll_periods', sa.Column('paid_outside_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('payroll_periods', sa.Column('paid_outside_by_id', sa.Integer(),
                                               sa.ForeignKey('users.id', name='fk_payroll_periods_paid_outside_by'),
                                               nullable=True))


def downgrade() -> None:
    op.drop_constraint('fk_payroll_periods_paid_outside_by', 'payroll_periods', type_='foreignkey')
    op.drop_column('payroll_periods', 'paid_outside_by_id')
    op.drop_column('payroll_periods', 'paid_outside_at')
