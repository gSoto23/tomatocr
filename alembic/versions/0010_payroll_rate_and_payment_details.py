"""payroll keeps its hourly rate; payments keep method, reference and payroll

Each payroll entry stores the hourly rate used when the payroll was generated, so
changing someone's rate later no longer changes old payrolls. Existing entries get
the person's current rate (what they were being shown with until now).
Payroll payments record how they were paid (method and reference) and, optionally,
which payroll they settle.

Revision ID: 0010
Revises: 0009
Create Date: 2026-09-28 20:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0010'
down_revision: Union[str, None] = '0009'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('payroll_entries', sa.Column('hourly_rate', sa.Float(), nullable=True))
    op.execute("UPDATE payroll_entries SET hourly_rate = "
               "(SELECT users.hourly_rate FROM users WHERE users.id = payroll_entries.user_id)")
    op.add_column('payroll_payments', sa.Column('method', sa.String(length=30), nullable=True))
    op.add_column('payroll_payments', sa.Column('reference', sa.String(length=100), nullable=True))
    op.add_column('payroll_payments', sa.Column('payroll_period_id', sa.Integer(), nullable=True))
    op.create_foreign_key('fk_payroll_payments_period', 'payroll_payments', 'payroll_periods',
                          ['payroll_period_id'], ['id'], ondelete='SET NULL')


def downgrade() -> None:
    op.drop_constraint('fk_payroll_payments_period', 'payroll_payments', type_='foreignkey')
    for column in ('payroll_period_id', 'reference', 'method'):
        op.drop_column('payroll_payments', column)
    op.drop_column('payroll_entries', 'hourly_rate')
