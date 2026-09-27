"""crm accounts

Fase 2A (docs/DISENO_CRM.md, adjusted by docs/ANALISIS_ENCAJE_CRM.md): accounts
(status computed, only discarded_at stored), one contact list per account,
project_contact_roles (site contacts and report recipients per project),
opportunities, follow-ups (crm_activities) and reviewed non-duplicate pairs;
optional account/opportunity links on projects, quotes and reforestation
projects. No existing column changes.

Revision ID: 0003
Revises: 0002
Create Date: 2026-09-27 09:41:03.079383

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0003'
down_revision: Union[str, None] = '0002'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('accounts',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=200), nullable=False),
    sa.Column('legal_name', sa.String(length=200), nullable=True),
    sa.Column('tax_id', sa.String(length=30), nullable=True),
    sa.Column('kind', sa.String(length=30), server_default='otro', nullable=False),
    sa.Column('discarded_at', sa.DateTime(), nullable=True),
    sa.Column('source', sa.String(length=30), nullable=True),
    sa.Column('owner_id', sa.Integer(), nullable=True),
    sa.Column('province', sa.String(length=50), nullable=True),
    sa.Column('address', sa.Text(), nullable=True),
    sa.Column('website', sa.String(length=200), nullable=True),
    sa.Column('vat_exemption_code', sa.String(length=50), nullable=True),
    sa.Column('notes', sa.Text(), nullable=True),
    sa.Column('origin_ref', sa.String(length=50), nullable=True),
    sa.Column('merged_into_id', sa.Integer(), nullable=True),
    sa.Column('created_by_id', sa.Integer(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=True),
    sa.Column('updated_at', sa.DateTime(), nullable=True),
    sa.ForeignKeyConstraint(['created_by_id'], ['users.id'], ),
    sa.ForeignKeyConstraint(['merged_into_id'], ['accounts.id'], ),
    sa.ForeignKeyConstraint(['owner_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('tax_id')
    )
    op.create_index(op.f('ix_accounts_id'), 'accounts', ['id'], unique=False)
    op.create_index(op.f('ix_accounts_name'), 'accounts', ['name'], unique=False)
    op.create_table('account_not_duplicates',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('account_a_id', sa.Integer(), nullable=False),
    sa.Column('account_b_id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=True),
    sa.ForeignKeyConstraint(['account_a_id'], ['accounts.id'], ),
    sa.ForeignKeyConstraint(['account_b_id'], ['accounts.id'], ),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('account_a_id', 'account_b_id', name='uq_account_not_duplicates_pair')
    )
    op.create_table('contacts',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('account_id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=150), nullable=False),
    sa.Column('role_title', sa.String(length=100), nullable=True),
    sa.Column('email', sa.String(length=150), nullable=True),
    sa.Column('phone', sa.String(length=30), nullable=True),
    sa.Column('is_primary', sa.Boolean(), server_default='false', nullable=False),
    sa.Column('is_commercial', sa.Boolean(), server_default='false', nullable=False),
    sa.Column('is_billing', sa.Boolean(), server_default='false', nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=True),
    sa.Column('consent_marketing', sa.Boolean(), server_default='false', nullable=False),
    sa.Column('consent_at', sa.DateTime(), nullable=True),
    sa.Column('consent_text_version', sa.String(length=20), nullable=True),
    sa.Column('notes', sa.Text(), nullable=True),
    sa.Column('origin_ref', sa.String(length=50), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=True),
    sa.Column('updated_at', sa.DateTime(), nullable=True),
    sa.ForeignKeyConstraint(['account_id'], ['accounts.id'], ),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('user_id')
    )
    op.create_index(op.f('ix_contacts_account_id'), 'contacts', ['account_id'], unique=False)
    op.create_index(op.f('ix_contacts_email'), 'contacts', ['email'], unique=False)
    op.create_index(op.f('ix_contacts_id'), 'contacts', ['id'], unique=False)
    op.create_table('opportunities',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('account_id', sa.Integer(), nullable=False),
    sa.Column('title', sa.String(length=200), nullable=False),
    sa.Column('kind', sa.String(length=20), server_default='nuevo', nullable=False),
    sa.Column('motor', sa.String(length=30), nullable=True),
    sa.Column('stage', sa.String(length=20), server_default='prospecto', nullable=False),
    sa.Column('max_stage', sa.Integer(), server_default='0', nullable=False),
    sa.Column('lost_reason', sa.Text(), nullable=True),
    sa.Column('amount_crc', sa.Float(), nullable=True),
    sa.Column('expected_close_date', sa.Date(), nullable=True),
    sa.Column('owner_id', sa.Integer(), nullable=True),
    sa.Column('next_step', sa.String(length=255), nullable=True),
    sa.Column('next_step_date', sa.Date(), nullable=True),
    sa.Column('source', sa.String(length=30), nullable=True),
    sa.Column('project_id', sa.Integer(), nullable=True),
    sa.Column('created_by_id', sa.Integer(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=True),
    sa.Column('updated_at', sa.DateTime(), nullable=True),
    sa.ForeignKeyConstraint(['account_id'], ['accounts.id'], ),
    sa.ForeignKeyConstraint(['created_by_id'], ['users.id'], ),
    sa.ForeignKeyConstraint(['owner_id'], ['users.id'], ),
    sa.ForeignKeyConstraint(['project_id'], ['projects.id'], name='fk_opportunities_project_id'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_opportunities_account_id'), 'opportunities', ['account_id'], unique=False)
    op.create_index(op.f('ix_opportunities_id'), 'opportunities', ['id'], unique=False)
    op.create_table('crm_activities',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('account_id', sa.Integer(), nullable=False),
    sa.Column('opportunity_id', sa.Integer(), nullable=True),
    sa.Column('contact_id', sa.Integer(), nullable=True),
    sa.Column('type', sa.String(length=20), nullable=False),
    sa.Column('happened_at', sa.DateTime(), nullable=False),
    sa.Column('notes', sa.Text(), nullable=True),
    sa.Column('user_id', sa.Integer(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=True),
    sa.ForeignKeyConstraint(['account_id'], ['accounts.id'], ),
    sa.ForeignKeyConstraint(['contact_id'], ['contacts.id'], ),
    sa.ForeignKeyConstraint(['opportunity_id'], ['opportunities.id'], ),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_crm_activities_account_id'), 'crm_activities', ['account_id'], unique=False)
    op.create_index(op.f('ix_crm_activities_id'), 'crm_activities', ['id'], unique=False)
    op.create_table('project_contact_roles',
    sa.Column('project_id', sa.Integer(), nullable=False),
    sa.Column('contact_id', sa.Integer(), nullable=False),
    sa.Column('is_site', sa.Boolean(), server_default='true', nullable=False),
    sa.Column('receives_reports', sa.Boolean(), server_default='false', nullable=False),
    sa.Column('position', sa.String(length=100), nullable=True),
    sa.ForeignKeyConstraint(['contact_id'], ['contacts.id'], ),
    sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ),
    sa.PrimaryKeyConstraint('project_id', 'contact_id')
    )
    op.add_column('projects', sa.Column('account_id', sa.Integer(), nullable=True))
    op.add_column('projects', sa.Column('opportunity_id', sa.Integer(), nullable=True))
    op.create_index(op.f('ix_projects_account_id'), 'projects', ['account_id'], unique=False)
    op.create_foreign_key('fk_projects_account_id', 'projects', 'accounts', ['account_id'], ['id'])
    op.create_foreign_key('fk_projects_opportunity_id', 'projects', 'opportunities', ['opportunity_id'], ['id'])
    op.add_column('quotes', sa.Column('account_id', sa.Integer(), nullable=True))
    op.add_column('quotes', sa.Column('opportunity_id', sa.Integer(), nullable=True))
    op.create_index(op.f('ix_quotes_account_id'), 'quotes', ['account_id'], unique=False)
    op.create_foreign_key('fk_quotes_account_id', 'quotes', 'accounts', ['account_id'], ['id'])
    op.create_foreign_key('fk_quotes_opportunity_id', 'quotes', 'opportunities', ['opportunity_id'], ['id'])
    op.add_column('reforestation_projects', sa.Column('account_id', sa.Integer(), nullable=True))
    op.create_index(op.f('ix_reforestation_projects_account_id'), 'reforestation_projects', ['account_id'], unique=False)
    op.create_foreign_key('fk_reforestation_projects_account_id', 'reforestation_projects', 'accounts', ['account_id'], ['id'])


def downgrade() -> None:
    op.drop_constraint('fk_reforestation_projects_account_id', 'reforestation_projects', type_='foreignkey')
    op.drop_index(op.f('ix_reforestation_projects_account_id'), table_name='reforestation_projects')
    op.drop_column('reforestation_projects', 'account_id')
    op.drop_constraint('fk_quotes_opportunity_id', 'quotes', type_='foreignkey')
    op.drop_constraint('fk_quotes_account_id', 'quotes', type_='foreignkey')
    op.drop_index(op.f('ix_quotes_account_id'), table_name='quotes')
    op.drop_column('quotes', 'opportunity_id')
    op.drop_column('quotes', 'account_id')
    op.drop_constraint('fk_projects_opportunity_id', 'projects', type_='foreignkey')
    op.drop_constraint('fk_projects_account_id', 'projects', type_='foreignkey')
    op.drop_index(op.f('ix_projects_account_id'), table_name='projects')
    op.drop_column('projects', 'opportunity_id')
    op.drop_column('projects', 'account_id')
    op.drop_table('project_contact_roles')
    op.drop_index(op.f('ix_crm_activities_id'), table_name='crm_activities')
    op.drop_index(op.f('ix_crm_activities_account_id'), table_name='crm_activities')
    op.drop_table('crm_activities')
    op.drop_index(op.f('ix_opportunities_id'), table_name='opportunities')
    op.drop_index(op.f('ix_opportunities_account_id'), table_name='opportunities')
    op.drop_table('opportunities')
    op.drop_index(op.f('ix_contacts_id'), table_name='contacts')
    op.drop_index(op.f('ix_contacts_email'), table_name='contacts')
    op.drop_index(op.f('ix_contacts_account_id'), table_name='contacts')
    op.drop_table('contacts')
    op.drop_table('account_not_duplicates')
    op.drop_index(op.f('ix_accounts_name'), table_name='accounts')
    op.drop_index(op.f('ix_accounts_id'), table_name='accounts')
    op.drop_table('accounts')
