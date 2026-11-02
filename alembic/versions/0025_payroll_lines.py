"""planilla: líneas (bonos, comisiones, ajustes, viáticos, deducciones, adelantos), ajustes para
la próxima planilla y viáticos fijos por quincena

Revision ID: 0025
Revises: 0024
Create Date: 2026-10-30 16:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0025'
down_revision: Union[str, None] = '0024'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'payroll_adjustments',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('kind', sa.String(length=20), nullable=False),
        sa.Column('description', sa.String(length=200), nullable=False),
        sa.Column('amount', sa.Float(), nullable=False),
        sa.Column('source_period_id', sa.Integer(), sa.ForeignKey('payroll_periods.id', ondelete='SET NULL'),
                  nullable=True),
        sa.Column('created_by_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
    )
    op.create_index('ix_payroll_adjustments_id', 'payroll_adjustments', ['id'])
    op.create_index('ix_payroll_adjustments_user_id', 'payroll_adjustments', ['user_id'])
    op.create_table(
        'payroll_lines',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('entry_id', sa.Integer(), sa.ForeignKey('payroll_entries.id', ondelete='CASCADE'), nullable=False),
        sa.Column('kind', sa.String(length=20), nullable=False),
        sa.Column('description', sa.String(length=200), nullable=False),
        sa.Column('amount', sa.Float(), nullable=False),
        sa.Column('adjustment_id', sa.Integer(), sa.ForeignKey('payroll_adjustments.id', ondelete='SET NULL'),
                  nullable=True),
        sa.Column('created_by_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
    )
    op.create_index('ix_payroll_lines_id', 'payroll_lines', ['id'])
    op.create_index('ix_payroll_lines_entry_id', 'payroll_lines', ['entry_id'])
    op.add_column('payroll_entries', sa.Column('base_salary', sa.Float(), nullable=True))
    # Existing entries have no lines: their base is their gross.
    op.execute("UPDATE payroll_entries SET base_salary = gross_salary")
    op.add_column('users', sa.Column('viatico_quincenal', sa.Float(), server_default='0', nullable=False))


def downgrade() -> None:
    op.drop_column('users', 'viatico_quincenal')
    op.drop_column('payroll_entries', 'base_salary')
    op.drop_index('ix_payroll_lines_entry_id', table_name='payroll_lines')
    op.drop_index('ix_payroll_lines_id', table_name='payroll_lines')
    op.drop_table('payroll_lines')
    op.drop_index('ix_payroll_adjustments_user_id', table_name='payroll_adjustments')
    op.drop_index('ix_payroll_adjustments_id', table_name='payroll_adjustments')
    op.drop_table('payroll_adjustments')
