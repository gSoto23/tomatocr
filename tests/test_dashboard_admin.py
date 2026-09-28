"""Admin Dashboard: what needs attention, today in the field and the money."""
from datetime import date, timedelta

from app.db.models.finance import BudgetLine, Invoice, InvoiceStatus, ProjectBudget
from app.db.models.log import DailyLog
from app.db.models.payroll import PayrollPeriod
from app.db.models.schedule import ProjectSchedule
from app.utils.admin_overview import admin_overview
from app.utils.timecr import today_cr


def test_overview_finds_what_needs_attention(db, users):
    today = today_cr()
    pid, worker = users["project_id"], users["worker"].id
    budget = ProjectBudget(project_id=pid)
    db.add(budget)
    db.flush()
    line = BudgetLine(budget_id=budget.id, name="L", subtotal=1000, tax_percentage=0)
    db.add(line)
    db.flush()
    db.add(Invoice(budget_id=budget.id, budget_line_id=line.id, invoice_number="F1", amount=300,
                   issue_date=today, due_date=today - timedelta(days=5), status=InvoiceStatus.OVERDUE))
    db.add_all([ProjectSchedule(project_id=pid, user_id=worker, date=today),
                ProjectSchedule(project_id=pid, user_id=worker, date=today - timedelta(days=2)),
                ProjectSchedule(project_id=pid, user_id=worker, date=today - timedelta(days=3), is_confirmed=True)])
    db.add(DailyLog(project_id=pid, user_id=worker, date=today - timedelta(days=3), notes="ok"))
    db.add(PayrollPeriod(start_date=today - timedelta(days=14), end_date=today - timedelta(days=1), status="draft"))
    db.commit()
    ov = admin_overview(db, today)
    titles = [a.title for a in ov.alerts]
    assert titles[0] == "1 factura vencida"
    assert "1 día trabajado sin bitácora" in titles  # 2 days ago; the 3rd day has its report
    assert "1 jornada con horas sin confirmar" in titles and "1 planilla en borrador" in titles
    assert [d.project.id for d in ov.in_field] == [pid] and not ov.in_field[0].reported
    assert ov.money["receivable"] == 300 and ov.money["overdue"] == 300 and ov.money["to_invoice"] == 700
    assert ov.money["invoiced_month"] == 300


def test_dashboard_shows_the_sections(login_as):
    html = login_as("admin").get("/dashboard").text
    for text in ("Requiere atención", "Hoy en campo", "Dinero", "Por cobrar", "Por facturar", "Facturas por cobrar"):
        assert text in html, text

