"""planilla: comisiones de los vendedores (por factura pagada y por cliente nuevo)

Revision ID: 0026
Revises: 0025
Create Date: 2026-11-02 10:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0026'
down_revision: Union[str, None] = '0025'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'commissions',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('kind', sa.String(length=20), nullable=False),
        sa.Column('invoice_id', sa.Integer(), sa.ForeignKey('invoices.id', ondelete='SET NULL'), nullable=True),
        sa.Column('project_id', sa.Integer(), sa.ForeignKey('projects.id', ondelete='SET NULL'), nullable=True),
        sa.Column('opportunity_id', sa.Integer(), sa.ForeignKey('opportunities.id', ondelete='SET NULL'),
                  nullable=True),
        sa.Column('account_id', sa.Integer(), sa.ForeignKey('accounts.id', ondelete='SET NULL'), nullable=True),
        sa.Column('client_name', sa.String(length=200), nullable=True),
        sa.Column('invoice_number', sa.String(length=50), nullable=True),
        sa.Column('payment_date', sa.Date(), nullable=True),
        sa.Column('base_amount', sa.Float(), nullable=True),
        sa.Column('rate', sa.Float(), nullable=True),
        sa.Column('amount', sa.Float(), nullable=False),
        sa.Column('adjustment_id', sa.Integer(), sa.ForeignKey('payroll_adjustments.id', ondelete='SET NULL'),
                  nullable=True),
        sa.Column('reversal_adjustment_id', sa.Integer(),
                  sa.ForeignKey('payroll_adjustments.id', ondelete='SET NULL'), nullable=True),
        sa.Column('cancelled_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('cancel_reason', sa.String(length=255), nullable=True),
        sa.Column('cancelled_by_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
    )
    op.create_index('ix_commissions_id', 'commissions', ['id'])
    op.create_index('ix_commissions_user_id', 'commissions', ['user_id'])
    op.create_index('ix_commissions_invoice_id', 'commissions', ['invoice_id'])
    op.create_index('ix_commissions_opportunity_id', 'commissions', ['opportunity_id'])
    op.add_column('users', sa.Column('commission_percent', sa.Float(), nullable=True))
    op.add_column('users', sa.Column('commission_new_client', sa.Float(), nullable=True))


def downgrade() -> None:
    op.drop_column('users', 'commission_new_client')
    op.drop_column('users', 'commission_percent')
    for index in ('ix_commissions_opportunity_id', 'ix_commissions_invoice_id', 'ix_commissions_user_id',
                  'ix_commissions_id'):
        op.drop_index(index, table_name='commissions')
    op.drop_table('commissions')
