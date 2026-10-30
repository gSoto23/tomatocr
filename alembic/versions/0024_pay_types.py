"""planilla: forma de pago por persona (hora, día, mensual), tarifa diaria y tipo de empleado

Revision ID: 0024
Revises: 0023
Create Date: 2026-10-30 13:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0024'
down_revision: Union[str, None] = '0023'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('users', sa.Column('pay_type', sa.String(length=10), server_default='hora', nullable=False))
    op.add_column('users', sa.Column('daily_rate', sa.Float(), server_default='0', nullable=False))
    op.add_column('users', sa.Column('employment_type', sa.String(length=12), server_default='fijo', nullable=False))
    op.add_column('payroll_entries', sa.Column('pay_type', sa.String(length=10), nullable=True))
    op.add_column('payroll_entries', sa.Column('days_worked', sa.Float(), nullable=True))
    # Asesores (ventas) earn a monthly salary; everyone else keeps being paid by the hour.
    op.execute("UPDATE users SET pay_type = 'mensual' WHERE role = 'ventas'")


def downgrade() -> None:
    op.drop_column('payroll_entries', 'days_worked')
    op.drop_column('payroll_entries', 'pay_type')
    op.drop_column('users', 'employment_type')
    op.drop_column('users', 'daily_rate')
    op.drop_column('users', 'pay_type')
