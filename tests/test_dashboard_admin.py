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



# --- The other roles ------------------------------------------------------------------------

def schedule(db, users, who, days_ago, confirmed=False):
    s = ProjectSchedule(project_id=users["project_id"], user_id=users[who].id,
                        date=today_cr() - timedelta(days=days_ago), is_confirmed=confirmed)
    db.add(s)
    db.commit()
    return s


def test_supervisor_sees_the_team_but_not_own_hours(db, login_as, users):
    schedule(db, users, "worker", 0)
    schedule(db, users, "supervisor", 2)  # own: never asked to confirm it
    html = login_as("supervisor").get("/dashboard").text
    assert "Hoy en campo" in html and "Gestionar Calendario" in html
    assert "jornada con horas sin confirmar" not in html
    schedule(db, users, "worker", 3)
    assert "1 jornada con horas sin confirmar" in login_as("supervisor").get("/dashboard").text


def test_worker_is_reminded_of_days_without_report(db, login_as, users):
    schedule(db, users, "worker", 0)
    past = schedule(db, users, "worker", 2)
    html = login_as("worker").get("/dashboard").text
    assert "Te quedó 1 día sin bitácora" in html
    assert f"/logs/new?project_id={users['project_id']}&date={past.date.isoformat()}" in html
    assert "Registrar bitácora de hoy" in html


def test_report_form_takes_the_day_from_the_link(login_as, users):
    client = login_as("worker")
    day = (today_cr() - timedelta(days=2)).isoformat()
    assert f"reportDate: '{day}'" in client.get(f"/logs/new?project_id={users['project_id']}&date={day}").text
    too_old = (today_cr() - timedelta(days=30)).isoformat()
    assert f"reportDate: '{today_cr().isoformat()}'" in client.get(f"/logs/new?date={too_old}").text


def test_client_sees_each_project_with_next_visit_date_only(db, login_as, users):
    schedule(db, users, "worker", -3)  # in 3 days
    db.add(DailyLog(project_id=users["project_id"], user_id=users["worker"].id, date=today_cr(), notes="ok"))
    db.commit()
    html = login_as("client").get("/dashboard").text
    assert "Mis proyectos" in html and "Próxima visita" in html
    assert (today_cr() + timedelta(days=3)).strftime("%d/%m/%Y") in html
    cards = html.split("Mis proyectos", 1)[1].split("Bitácora Global", 1)[0]
    assert "u_worker" not in cards  # no staff names


def test_sales_sees_own_funnel(login_as):
    assert "Mi embudo" in login_as("ventas").get("/dashboard").text
