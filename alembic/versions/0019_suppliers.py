"""proveedores: suppliers and their contacts

Revision ID: 0019
Revises: 0018
Create Date: 2026-10-15 10:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0019'
down_revision: Union[str, None] = '0018'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'suppliers',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('name', sa.String(length=200), nullable=False),
        sa.Column('category', sa.String(length=20), server_default='otro', nullable=False),
        sa.Column('tax_id', sa.String(length=30), nullable=True),
        sa.Column('iban', sa.String(length=40), nullable=True),
        sa.Column('sinpe', sa.String(length=30), nullable=True),
        sa.Column('payment_terms', sa.String(length=60), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('created_by_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
    )
    op.create_index('ix_suppliers_id', 'suppliers', ['id'])
    op.create_index('ix_suppliers_category', 'suppliers', ['category'])
    op.create_table(
        'supplier_contacts',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('supplier_id', sa.Integer(), sa.ForeignKey('suppliers.id', ondelete='CASCADE'), nullable=False),
        sa.Column('name', sa.String(length=120), nullable=False),
        sa.Column('role', sa.String(length=80), nullable=True),
        sa.Column('phone', sa.String(length=30), nullable=True),
        sa.Column('email', sa.String(length=120), nullable=True),
    )
    op.create_index('ix_supplier_contacts_id', 'supplier_contacts', ['id'])
    op.create_index('ix_supplier_contacts_supplier_id', 'supplier_contacts', ['supplier_id'])


def downgrade() -> None:
    op.drop_index('ix_supplier_contacts_supplier_id', table_name='supplier_contacts')
    op.drop_index('ix_supplier_contacts_id', table_name='supplier_contacts')
    op.drop_table('supplier_contacts')
    op.drop_index('ix_suppliers_category', table_name='suppliers')
    op.drop_index('ix_suppliers_id', table_name='suppliers')
    op.drop_table('suppliers')
