"""quotes sent by e-mail from the quote tool

Revision ID: 0015
Revises: 0014
Create Date: 2026-09-30 10:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0015'
down_revision: Union[str, None] = '0014'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'quote_emails',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('quote_id', sa.Integer(), sa.ForeignKey('quotes.id', ondelete='CASCADE'), nullable=False),
        sa.Column('sent_at', sa.DateTime(), nullable=False),
        sa.Column('sent_by_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('recipients', sa.Text(), nullable=False),
        sa.Column('subject', sa.String(length=200), nullable=False),
        sa.Column('message', sa.Text(), nullable=True),
    )
    op.create_index('ix_quote_emails_id', 'quote_emails', ['id'])
    op.create_index('ix_quote_emails_quote_id', 'quote_emails', ['quote_id'])


def downgrade() -> None:
    op.drop_index('ix_quote_emails_quote_id', table_name='quote_emails')
    op.drop_index('ix_quote_emails_id', table_name='quote_emails')
    op.drop_table('quote_emails')
