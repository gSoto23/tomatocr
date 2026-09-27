"""quote discount and tax rate

The quote tool applied a discount and a VAT rate but never saved them, so a
reopened quote showed a different total. Existing quotes get 0 and 13 %.

Revision ID: 0005
Revises: 0004
Create Date: 2026-09-27 11:01:24.888629

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0005'
down_revision: Union[str, None] = '0004'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('quotes', sa.Column('discount', sa.Float(), server_default='0', nullable=False))
    op.add_column('quotes', sa.Column('tax_rate', sa.Float(), server_default='13', nullable=False))


def downgrade() -> None:
    op.drop_column('quotes', 'tax_rate')
    op.drop_column('quotes', 'discount')
