"""base schema

The full schema as of Fase 0, generated from the models and checked against
the production SQLite schema (same tables, columns, nullability and foreign
keys). Production PostgreSQL starts from an empty database with this revision.

Revision ID: 0001
Revises: 
Create Date: 2026-09-26 22:50:50.528183

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0001'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('login_attempts',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('username', sa.String(length=50), nullable=False),
    sa.Column('ip_address', sa.String(length=50), nullable=True),
    sa.Column('success', sa.Boolean(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_login_attempts_id'), 'login_attempts', ['id'], unique=False)
    op.create_index('ix_login_attempts_ip_created_at', 'login_attempts', ['ip_address', 'created_at'], unique=False)
    op.create_index('ix_login_attempts_username_created_at', 'login_attempts', ['username', 'created_at'], unique=False)
    op.create_table('payroll_periods',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('start_date', sa.Date(), nullable=False),
    sa.Column('end_date', sa.Date(), nullable=False),
    sa.Column('status', sa.String(length=20), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_payroll_periods_id'), 'payroll_periods', ['id'], unique=False)
    op.create_table('projects',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=100), nullable=False),
    sa.Column('location', sa.Text(), nullable=True),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('is_active', sa.Boolean(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
    sa.Column('client_display_name', sa.String(length=100), nullable=True),
    sa.Column('province', sa.String(length=50), nullable=True),
    sa.Column('address', sa.Text(), nullable=True),
    sa.Column('waze_link', sa.String(length=500), nullable=True),
    sa.Column('contact_name', sa.String(length=100), nullable=True),
    sa.Column('contact_phone', sa.String(length=20), nullable=True),
    sa.Column('contact_email', sa.String(length=100), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_projects_id'), 'projects', ['id'], unique=False)
    op.create_index(op.f('ix_projects_name'), 'projects', ['name'], unique=False)
    op.create_table('quotes',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('numero_cotizacion', sa.String(length=50), nullable=False),
    sa.Column('fecha_emision', sa.Date(), nullable=False),
    sa.Column('cliente_nombre', sa.String(length=200), nullable=False),
    sa.Column('cliente_datos', sa.JSON(), nullable=True),
    sa.Column('moneda', sa.String(length=10), nullable=True),
    sa.Column('tipo_servicio', sa.String(length=100), nullable=True),
    sa.Column('frecuencia', sa.String(length=50), nullable=True),
    sa.Column('validez_dias', sa.Integer(), nullable=True),
    sa.Column('notes', sa.Text(), nullable=True),
    sa.Column('terminos', sa.Text(), nullable=True),
    sa.Column('subtotal', sa.Float(), nullable=True),
    sa.Column('iva', sa.Float(), nullable=True),
    sa.Column('total', sa.Float(), nullable=True),
    sa.Column('items', sa.JSON(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_quotes_id'), 'quotes', ['id'], unique=False)
    op.create_index(op.f('ix_quotes_numero_cotizacion'), 'quotes', ['numero_cotizacion'], unique=True)
    op.create_table('reforestation_projects',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('client_name', sa.String(length=255), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_reforestation_projects_client_name'), 'reforestation_projects', ['client_name'], unique=False)
    op.create_index(op.f('ix_reforestation_projects_id'), 'reforestation_projects', ['id'], unique=False)
    op.create_table('users',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('username', sa.String(length=50), nullable=False),
    sa.Column('hashed_password', sa.String(length=255), nullable=False),
    sa.Column('full_name', sa.String(length=100), nullable=True),
    sa.Column('role', sa.String(length=20), nullable=True),
    sa.Column('is_active', sa.Boolean(), nullable=True),
    sa.Column('apply_deductions', sa.Boolean(), nullable=True),
    sa.Column('phone', sa.String(length=20), nullable=True),
    sa.Column('email', sa.String(length=100), nullable=True),
    sa.Column('start_date', sa.Date(), nullable=True),
    sa.Column('hourly_rate', sa.Float(), nullable=True),
    sa.Column('monthly_salary', sa.Float(), nullable=True),
    sa.Column('status', sa.Enum('active', 'inactive', 'liquidated', name='worker_status'), nullable=True),
    sa.Column('payment_method', sa.String(length=20), nullable=True),
    sa.Column('account_number', sa.String(length=50), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_users_id'), 'users', ['id'], unique=False)
    op.create_index(op.f('ix_users_username'), 'users', ['username'], unique=True)
    op.create_table('activity_logs',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=True),
    sa.Column('action', sa.String(length=50), nullable=True),
    sa.Column('entity_type', sa.String(length=50), nullable=True),
    sa.Column('entity_id', sa.Integer(), nullable=True),
    sa.Column('details', sa.Text(), nullable=True),
    sa.Column('ip_address', sa.String(length=50), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=True),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_activity_logs_id'), 'activity_logs', ['id'], unique=False)
    op.create_table('liquidations',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('date', sa.Date(), nullable=False),
    sa.Column('total_amount', sa.Float(), nullable=True),
    sa.Column('vacation_days', sa.Float(), nullable=True),
    sa.Column('vacation_amount', sa.Float(), nullable=True),
    sa.Column('aguinaldo_amount', sa.Float(), nullable=True),
    sa.Column('salary_due', sa.Float(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
    sa.Column('created_by_id', sa.Integer(), nullable=True),
    sa.ForeignKeyConstraint(['created_by_id'], ['users.id'], ),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_liquidations_id'), 'liquidations', ['id'], unique=False)
    op.create_table('payroll_entries',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('payroll_period_id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('total_hours', sa.Float(), nullable=True),
    sa.Column('overtime_hours', sa.Float(), nullable=True),
    sa.Column('gross_salary', sa.Float(), nullable=True),
    sa.Column('social_charges', sa.Float(), nullable=True),
    sa.Column('net_salary', sa.Float(), nullable=True),
    sa.Column('apply_deductions', sa.Boolean(), nullable=True),
    sa.Column('details', sa.JSON(), nullable=True),
    sa.ForeignKeyConstraint(['payroll_period_id'], ['payroll_periods.id'], ),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_payroll_entries_id'), 'payroll_entries', ['id'], unique=False)
    op.create_table('payroll_payments',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('amount', sa.Float(), nullable=False),
    sa.Column('hours_paid', sa.Float(), nullable=True),
    sa.Column('overtime_hours', sa.Float(), nullable=True),
    sa.Column('date', sa.Date(), nullable=False),
    sa.Column('notes', sa.String(length=255), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
    sa.Column('created_by_id', sa.Integer(), nullable=True),
    sa.ForeignKeyConstraint(['created_by_id'], ['users.id'], ),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_payroll_payments_id'), 'payroll_payments', ['id'], unique=False)
    op.create_table('project_budgets',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('project_id', sa.Integer(), nullable=False),
    sa.Column('licitation_number', sa.String(), nullable=True),
    sa.Column('contract_duration', sa.String(), nullable=True),
    sa.Column('is_prorrogable', sa.Boolean(), nullable=True),
    sa.Column('prorrogable_time', sa.String(), nullable=True),
    sa.Column('prorrogable_amount', sa.Float(), nullable=True),
    sa.Column('active_prorogue', sa.Boolean(), nullable=True),
    sa.Column('start_date', sa.Date(), nullable=True),
    sa.Column('end_date', sa.Date(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('project_id')
    )
    op.create_index(op.f('ix_project_budgets_id'), 'project_budgets', ['id'], unique=False)
    op.create_table('project_contacts',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('project_id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=100), nullable=False),
    sa.Column('phone', sa.String(length=20), nullable=True),
    sa.Column('email', sa.String(length=100), nullable=True),
    sa.Column('position', sa.String(length=100), nullable=True),
    sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_project_contacts_id'), 'project_contacts', ['id'], unique=False)
    op.create_table('project_costs',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('project_id', sa.Integer(), nullable=False),
    sa.Column('date', sa.Date(), nullable=False),
    sa.Column('description', sa.String(), nullable=False),
    sa.Column('amount', sa.Float(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
    sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_project_costs_id'), 'project_costs', ['id'], unique=False)
    op.create_table('project_locations',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('project_id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=100), nullable=False),
    sa.Column('location', sa.String(length=255), nullable=True),
    sa.Column('waze_pin', sa.String(length=500), nullable=True),
    sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_project_locations_id'), 'project_locations', ['id'], unique=False)
    op.create_table('project_supplies',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('project_id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=100), nullable=False),
    sa.Column('quantity', sa.String(length=50), nullable=True),
    sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_project_supplies_id'), 'project_supplies', ['id'], unique=False)
    op.create_table('project_tasks',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('project_id', sa.Integer(), nullable=False),
    sa.Column('description', sa.String(length=255), nullable=False),
    sa.Column('is_required', sa.Boolean(), nullable=True),
    sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_project_tasks_id'), 'project_tasks', ['id'], unique=False)
    op.create_table('project_users',
    sa.Column('project_id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('project_id', 'user_id')
    )
    op.create_table('reforestation_trees',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('project_id', sa.Integer(), nullable=True),
    sa.Column('tree_number', sa.Integer(), nullable=True),
    sa.Column('species', sa.String(length=255), nullable=True),
    sa.Column('lat', sa.Float(), nullable=True),
    sa.Column('lng', sa.Float(), nullable=True),
    sa.Column('sector_name', sa.String(length=255), nullable=True),
    sa.Column('date_planted', sa.Date(), nullable=True),
    sa.ForeignKeyConstraint(['project_id'], ['reforestation_projects.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_reforestation_trees_id'), 'reforestation_trees', ['id'], unique=False)
    op.create_index(op.f('ix_reforestation_trees_tree_number'), 'reforestation_trees', ['tree_number'], unique=False)
    op.create_table('user_documents',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('filename', sa.String(length=255), nullable=False),
    sa.Column('file_path', sa.String(length=500), nullable=False),
    sa.Column('document_type', sa.String(length=50), nullable=True),
    sa.Column('upload_date', sa.DateTime(), nullable=True),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_user_documents_id'), 'user_documents', ['id'], unique=False)
    op.create_table('budget_lines',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('budget_id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(), nullable=False),
    sa.Column('subtotal', sa.Float(), nullable=True),
    sa.Column('tax_percentage', sa.Float(), nullable=True),
    sa.ForeignKeyConstraint(['budget_id'], ['project_budgets.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_budget_lines_id'), 'budget_lines', ['id'], unique=False)
    op.create_table('daily_logs',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('project_id', sa.Integer(), nullable=False),
    sa.Column('location_id', sa.Integer(), nullable=True),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('date', sa.Date(), nullable=False),
    sa.Column('notes', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['location_id'], ['project_locations.id'], ),
    sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_daily_logs_id'), 'daily_logs', ['id'], unique=False)
    op.create_table('project_schedules',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('project_id', sa.Integer(), nullable=False),
    sa.Column('location_id', sa.Integer(), nullable=True),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('date', sa.Date(), nullable=False),
    sa.Column('hours_worked', sa.Float(), nullable=True),
    sa.Column('overtime_hours', sa.Float(), nullable=True),
    sa.Column('is_confirmed', sa.Boolean(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
    sa.ForeignKeyConstraint(['location_id'], ['project_locations.id'], ),
    sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_project_schedules_date'), 'project_schedules', ['date'], unique=False)
    op.create_index(op.f('ix_project_schedules_id'), 'project_schedules', ['id'], unique=False)
    op.create_table('daily_log_tasks',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('log_id', sa.Integer(), nullable=False),
    sa.Column('task_id', sa.Integer(), nullable=False),
    sa.Column('completed', sa.Boolean(), nullable=True),
    sa.Column('notes', sa.String(length=255), nullable=True),
    sa.ForeignKeyConstraint(['log_id'], ['daily_logs.id'], ),
    sa.ForeignKeyConstraint(['task_id'], ['project_tasks.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_daily_log_tasks_id'), 'daily_log_tasks', ['id'], unique=False)
    op.create_table('invoices',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('budget_id', sa.Integer(), nullable=False),
    sa.Column('budget_line_id', sa.Integer(), nullable=False),
    sa.Column('invoice_number', sa.String(), nullable=False),
    sa.Column('issue_date', sa.Date(), nullable=False),
    sa.Column('due_date', sa.Date(), nullable=False),
    sa.Column('amount', sa.Float(), nullable=True),
    sa.Column('status', sa.Enum('PENDING', 'OVERDUE', 'PAID', 'PARTIAL', name='invoicestatus'), nullable=True),
    sa.Column('note', sa.String(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
    sa.ForeignKeyConstraint(['budget_id'], ['project_budgets.id'], ),
    sa.ForeignKeyConstraint(['budget_line_id'], ['budget_lines.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_invoices_id'), 'invoices', ['id'], unique=False)
    op.create_table('photos',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('log_id', sa.Integer(), nullable=False),
    sa.Column('file_path', sa.String(length=255), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
    sa.ForeignKeyConstraint(['log_id'], ['daily_logs.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_photos_id'), 'photos', ['id'], unique=False)
    op.create_table('schedule_tasks',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('schedule_id', sa.Integer(), nullable=False),
    sa.Column('title', sa.String(length=100), nullable=True),
    sa.Column('description', sa.String(length=255), nullable=False),
    sa.Column('completed', sa.Boolean(), nullable=True),
    sa.ForeignKeyConstraint(['schedule_id'], ['project_schedules.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_schedule_tasks_id'), 'schedule_tasks', ['id'], unique=False)
    op.create_table('payments',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('invoice_id', sa.Integer(), nullable=False),
    sa.Column('payment_date', sa.Date(), nullable=False),
    sa.Column('deposit_number', sa.String(), nullable=True),
    sa.Column('amount', sa.Float(), nullable=False),
    sa.Column('retention_amount', sa.Float(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
    sa.ForeignKeyConstraint(['invoice_id'], ['invoices.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('invoice_id')
    )
    op.create_index(op.f('ix_payments_id'), 'payments', ['id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_payments_id'), table_name='payments')
    op.drop_table('payments')
    op.drop_index(op.f('ix_schedule_tasks_id'), table_name='schedule_tasks')
    op.drop_table('schedule_tasks')
    op.drop_index(op.f('ix_photos_id'), table_name='photos')
    op.drop_table('photos')
    op.drop_index(op.f('ix_invoices_id'), table_name='invoices')
    op.drop_table('invoices')
    op.drop_index(op.f('ix_daily_log_tasks_id'), table_name='daily_log_tasks')
    op.drop_table('daily_log_tasks')
    op.drop_index(op.f('ix_project_schedules_id'), table_name='project_schedules')
    op.drop_index(op.f('ix_project_schedules_date'), table_name='project_schedules')
    op.drop_table('project_schedules')
    op.drop_index(op.f('ix_daily_logs_id'), table_name='daily_logs')
    op.drop_table('daily_logs')
    op.drop_index(op.f('ix_budget_lines_id'), table_name='budget_lines')
    op.drop_table('budget_lines')
    op.drop_index(op.f('ix_user_documents_id'), table_name='user_documents')
    op.drop_table('user_documents')
    op.drop_index(op.f('ix_reforestation_trees_tree_number'), table_name='reforestation_trees')
    op.drop_index(op.f('ix_reforestation_trees_id'), table_name='reforestation_trees')
    op.drop_table('reforestation_trees')
    op.drop_table('project_users')
    op.drop_index(op.f('ix_project_tasks_id'), table_name='project_tasks')
    op.drop_table('project_tasks')
    op.drop_index(op.f('ix_project_supplies_id'), table_name='project_supplies')
    op.drop_table('project_supplies')
    op.drop_index(op.f('ix_project_locations_id'), table_name='project_locations')
    op.drop_table('project_locations')
    op.drop_index(op.f('ix_project_costs_id'), table_name='project_costs')
    op.drop_table('project_costs')
    op.drop_index(op.f('ix_project_contacts_id'), table_name='project_contacts')
    op.drop_table('project_contacts')
    op.drop_index(op.f('ix_project_budgets_id'), table_name='project_budgets')
    op.drop_table('project_budgets')
    op.drop_index(op.f('ix_payroll_payments_id'), table_name='payroll_payments')
    op.drop_table('payroll_payments')
    op.drop_index(op.f('ix_payroll_entries_id'), table_name='payroll_entries')
    op.drop_table('payroll_entries')
    op.drop_index(op.f('ix_liquidations_id'), table_name='liquidations')
    op.drop_table('liquidations')
    op.drop_index(op.f('ix_activity_logs_id'), table_name='activity_logs')
    op.drop_table('activity_logs')
    op.drop_index(op.f('ix_users_username'), table_name='users')
    op.drop_index(op.f('ix_users_id'), table_name='users')
    op.drop_table('users')
    op.drop_index(op.f('ix_reforestation_projects_id'), table_name='reforestation_projects')
    op.drop_index(op.f('ix_reforestation_projects_client_name'), table_name='reforestation_projects')
    op.drop_table('reforestation_projects')
    op.drop_index(op.f('ix_quotes_numero_cotizacion'), table_name='quotes')
    op.drop_index(op.f('ix_quotes_id'), table_name='quotes')
    op.drop_table('quotes')
    op.drop_index(op.f('ix_projects_name'), table_name='projects')
    op.drop_index(op.f('ix_projects_id'), table_name='projects')
    op.drop_table('projects')
    op.drop_index(op.f('ix_payroll_periods_id'), table_name='payroll_periods')
    op.drop_table('payroll_periods')
    op.drop_index('ix_login_attempts_username_created_at', table_name='login_attempts')
    op.drop_index('ix_login_attempts_ip_created_at', table_name='login_attempts')
    op.drop_index(op.f('ix_login_attempts_id'), table_name='login_attempts')
    op.drop_table('login_attempts')
    sa.Enum(name='invoicestatus').drop(op.get_bind(), checkfirst=True)
    sa.Enum(name='worker_status').drop(op.get_bind(), checkfirst=True)
