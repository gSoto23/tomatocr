"""tree visits: several photos, public comment, GPS; tree location source and updated_at

For the public map's tree card and the darboles.com sync (docs/INTEGRACION_DARBOLES.md,
"Sincronización de árboles").

Revision ID: 0016
Revises: 0015
Create Date: 2026-09-30 16:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0016'
down_revision: Union[str, None] = '0015'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('tree_checks', sa.Column('public_comment', sa.String(length=500), nullable=True))
    op.add_column('tree_checks', sa.Column('lat', sa.Float(), nullable=True))
    op.add_column('tree_checks', sa.Column('lng', sa.Float(), nullable=True))
    op.add_column('tree_checks', sa.Column('accuracy_m', sa.Float(), nullable=True))
    op.add_column('reforestation_trees', sa.Column('location_source', sa.String(length=10),
                                                   server_default='sector', nullable=False))
    op.add_column('reforestation_trees', sa.Column('updated_at', sa.DateTime(), nullable=True))
    # Existing trees: last change = last visit, or now.
    op.execute("""
        UPDATE reforestation_trees SET updated_at = COALESCE(
            (SELECT MAX(c.created_at) FROM tree_checks c WHERE c.tree_id = reforestation_trees.id),
            CURRENT_TIMESTAMP)
    """)
    op.create_table(
        'tree_check_photos',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('check_id', sa.Integer(), sa.ForeignKey('tree_checks.id', ondelete='CASCADE'), nullable=False),
        sa.Column('url', sa.String(length=500), nullable=False),
        sa.Column('width', sa.Integer(), nullable=True),
        sa.Column('height', sa.Integer(), nullable=True),
        sa.Column('position', sa.Integer(), server_default='0', nullable=False),
    )
    op.create_index('ix_tree_check_photos_id', 'tree_check_photos', ['id'])
    op.create_index('ix_tree_check_photos_check_id', 'tree_check_photos', ['check_id'])
    op.create_index('ix_reforestation_trees_updated_at', 'reforestation_trees', ['updated_at'])


def downgrade() -> None:
    op.drop_index('ix_reforestation_trees_updated_at', table_name='reforestation_trees')
    op.drop_index('ix_tree_check_photos_check_id', table_name='tree_check_photos')
    op.drop_index('ix_tree_check_photos_id', table_name='tree_check_photos')
    op.drop_table('tree_check_photos')
    op.drop_column('reforestation_trees', 'updated_at')
    op.drop_column('reforestation_trees', 'location_source')
    op.drop_column('tree_checks', 'accuracy_m')
    op.drop_column('tree_checks', 'lng')
    op.drop_column('tree_checks', 'lat')
    op.drop_column('tree_checks', 'public_comment')
