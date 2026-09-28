"""UX round 3 (docs/PUNTOS_DIFICILES_UX.md, priority C, plus the calendar ranges):
navigation, error pages, amounts and dates, the quote tool, payroll and vacations,
calendar ranges and drag and drop, the employee list and reforestation."""
from datetime import date, datetime, timedelta

import pytest

from app.core.templates import crc_filter, format_datetime_cr_filter
from app.db.models.crm import Account, Opportunity
from app.db.models.log import DailyLog
from app.db.models.payment import PayrollPayment
from app.db.models.payroll import PayrollEntry, PayrollPeriod
from app.db.models.quote import Quote
from app.db.models.reforestation import ReforestationTree
from app.db.models.schedule import ProjectSchedule
from app.db.models.user import User
from app.utils.reforestation import survival_summary

HTML = {"accept": "text/html"}

# --- Navigation and errors ------------------------------------------------------------------


def test_forbidden_page_is_spanish_html_but_fetch_keeps_json(login_as):
    client = login_as("supervisor")
    page = client.get("/cotizador", headers=HTML)
    assert page.status_code == 403 and "text/html" in page.headers["content-type"]
    assert "No tenés acceso" in page.text and "Not authorized" not in page.text
    api = client.get("/api/quotes/", headers={"accept": "application/json"})
    assert api.status_code == 403 and api.json()["detail"]


def test_sidebar_shows_the_role_in_spanish_and_closes_on_tap(login_as):
    html = login_as("worker").get("/dashboard").text
    assert "Trabajador" in html and "$event.target.closest('a')" in html


def test_supervisor_has_no_budgets(login_as, users):
    client = login_as("supervisor")
    assert client.get("/finance/").status_code == 403
    assert client.get(f"/finance/{users['project_id']}").status_code == 403


@pytest.mark.parametrize("role,sees", [("admin", True), ("supervisor", False), ("worker", False), ("client", False)])
def test_project_costs_only_for_admin(login_as, users, role, sees):
    html = login_as(role).get(f"/projects/{users['project_id']}").text
    assert ("Costo Total del Proyecto" in html) == sees


# --- Amounts, dates and order ---------------------------------------------------------------

def test_amounts_and_dates_formats():
    assert crc_filter(1234.5) == "₡1,234.50" and crc_filter(-10) == "-₡10.00" and crc_filter(None) == "₡0.00"
    assert format_datetime_cr_filter(datetime(2026, 9, 28, 18, 30)) == "28/09/2026 12:30 PM"


def test_log_pages_keep_the_sort_order(db, login_as, users):
    for i in range(12):
        db.add(DailyLog(project_id=users["project_id"], user_id=users["worker"].id,
                        date=date.today() - timedelta(days=i), notes=f"n{i}"))
    db.commit()
    html = login_as("admin").get("/logs/?sort=project&order=asc").text
    assert "sort=project" in html and "order=asc" in html and "page=2" in html


# --- Quote tool -----------------------------------------------------------------------------

def test_client_without_account_cannot_save_invisible_quotes(login_as):
    data = {"numero_cotizacion": "TCR-2026-0500", "fecha_emision": date.today().isoformat(), "cliente_nombre": "X",
            "cliente_datos": {"name": "X"}, "moneda": "CRC", "total": 10, "items": []}
    response = login_as("client").post("/api/quotes/", json=data)
    assert response.status_code == 400 and "ligado a la cuenta" in response.json()["detail"]


def test_loaded_quote_brings_the_opportunity_title(db, login_as):
    account = Account(name="Hotel Bosque")
    db.add(account)
    db.flush()
    opp = Opportunity(account_id=account.id, title="Jardines del lobby")
    db.add(opp)
    db.flush()
    quote = Quote(numero_cotizacion="TCR-2026-0600", fecha_emision=date.today(), cliente_nombre="Hotel Bosque",
                  cliente_datos={"name": "Hotel Bosque"}, moneda="CRC", total=10, items=[], account_id=account.id,
                  opportunity_id=opp.id)
    db.add(quote)
    db.commit()
    assert login_as("ventas").get(f"/api/quotes/{quote.id}").json()["opportunity_title"] == "Jardines del lobby"


def test_cotizador_speaks_vos_and_fits_the_phone(login_as):
    html = login_as("ventas").get("/cotizador").text
    assert "Elegí el cliente" in html and "Elija" not in html and "<span>Volver</span>" in html


# --- Payroll and vacations ------------------------------------------------------------------

@pytest.fixture
def final_period(db, users):
    p = PayrollPeriod(start_date=date(2026, 9, 1), end_date=date(2026, 9, 15), status="final")
    db.add(p)
    db.flush()
    db.add(PayrollEntry(payroll_period_id=p.id, user_id=users["worker"].id, total_hours=80, gross_salary=1000,
                        social_charges=0, net_salary=1000, hourly_rate=10))
    db.commit()
    return p


def test_final_payroll_needs_the_word_and_no_payments(db, login_as, users, final_period):
    client = login_as("admin")
    assert client.delete(f"/payroll/{final_period.id}").status_code == 400
    db.add(PayrollPayment(user_id=users["worker"].id, amount=1000, date=date(2026, 9, 16),
                          payroll_period_id=final_period.id))
    db.commit()
    paid = client.delete(f"/payroll/{final_period.id}?confirm=ELIMINAR")
    assert paid.status_code == 400 and "pago" in paid.json()["detail"]
    db.query(PayrollPayment).delete()
    db.commit()
    assert client.delete(f"/payroll/{final_period.id}?confirm=eliminar").status_code == 200
    assert db.query(PayrollPeriod).count() == 0


def test_status_is_in_spanish(login_as, final_period):
    html = login_as("admin").get("/payroll/").text
    assert "Final" in html and ">\n                            final</span>" not in html


def test_vacation_balance_subtracts_days_taken(db, login_as, users):
    worker = db.get(User, users["worker"].id)
    worker.start_date = date.today() - timedelta(days=365)
    db.commit()
    client = login_as("admin")
    client.post(f"/users/{worker.id}/edit", data={"username": worker.username, "full_name": "Trabajador",
                                                  "role": "worker", "email": "t@example.com",
                                                  "vacation_days_taken": "4", "is_active": "true",
                                                  "payment_method": "Efectivo"}, follow_redirects=False)
    db.expire_all()
    assert db.get(User, worker.id).vacation_days_taken == 4
    html = login_as("worker").get("/payroll/").text
    assert "4.0 tomados" in html


def test_reactivation_takes_the_chosen_date_and_resets_vacations(db, login_as, users):
    worker = db.get(User, users["worker"].id)
    worker.status, worker.is_active, worker.vacation_days_taken = "liquidated", False, 3
    db.commit()
    login_as("admin").post(f"/liquidation/reactivate/{worker.id}", data={"start_date": "2026-10-01"},
                           follow_redirects=False)
    db.expire_all()
    worker = db.get(User, worker.id)
    assert (worker.start_date, worker.vacation_days_taken, worker.status) == (date(2026, 10, 1), 0, "active")


# --- Calendar ranges and drag and drop ------------------------------------------------------

@pytest.fixture
def week(db, login_as, users):
    client = login_as("admin")
    response = client.post("/calendar/schedule", data={"project_id": users["project_id"], "user_id": users["worker"].id,
                                                       "date": "2026-09-21", "end_date": "2026-09-25",
                                                       "tasks_json": '[{"title": "Corta", "description": ""}]'})
    assert response.status_code == 200
    return client, sorted(db.query(ProjectSchedule).all(), key=lambda s: s.date)


def test_events_know_their_range(week):
    client, days = week
    events = client.get("/calendar/events?start=2026-09-01&end=2026-09-30").json()
    assert {e["extendedProps"]["group_size"] for e in events} == {5}


def test_edit_the_whole_range(db, week, users):
    client, days = week
    response = client.post(f"/calendar/schedule/{days[0].id}/edit", data={
        "project_id": users["project_id"], "user_id": users["worker"].id, "date": days[0].date.isoformat(),
        "hours": 6, "scope": "group", "tasks_json": '[{"title": "Poda", "description": ""}]'})
    assert response.status_code == 200 and "5 asignaciones" in response.json()["message"]
    db.expire_all()
    assert {s.hours_worked for s in db.query(ProjectSchedule)} == {6}
    assert {t.title for s in db.query(ProjectSchedule) for t in s.tasks} == {"Poda"}


def test_delete_the_whole_range_or_one_day(db, week):
    client, days = week
    client.post(f"/calendar/schedule/{days[0].id}/delete", data={"scope": "one"})
    assert db.query(ProjectSchedule).count() == 4
    client.post(f"/calendar/schedule/{days[1].id}/delete", data={"scope": "group"})
    assert db.query(ProjectSchedule).count() == 0


def test_drag_moves_only_unconfirmed_days(db, week):
    client, days = week
    assert client.post(f"/calendar/schedule/{days[0].id}/move", data={"date": "2026-09-28"}).status_code == 200
    moved = client.post(f"/calendar/schedule/{days[1].id}/move", data={"date": "2026-09-28"})
    assert moved.status_code == 409  # the first one is already there
    days[2].is_confirmed = True
    db.commit()
    assert client.post(f"/calendar/schedule/{days[2].id}/move", data={"date": "2026-09-30"}).status_code == 400


# --- Employees ------------------------------------------------------------------------------

def test_employee_list_searches_sorts_and_shows_liquidated(db, login_as, users):
    worker = db.get(User, users["worker"].id)
    worker.full_name, worker.status, worker.is_active = "Zoila Liquidada", "liquidated", False
    db.commit()
    client = login_as("admin")
    table = client.get("/users/?q=zoila").text.split("<tbody", 1)[1].split("</tbody>", 1)[0]
    assert "Zoila Liquidada" in table and "Liquidado" in table and "u_supervisor" not in table
    html = table
    assert "Trabajador" in html
    assert client.get("/users/?sort=role").status_code == 200


# --- Reforestation --------------------------------------------------------------------------

def test_survival_at_three_months():
    today = date(2026, 9, 28)
    trees = [ReforestationTree(id=i, tree_number=i, status=s, date_planted=date(2026, 6, 1))
             for i, s in ((1, "vivo"), (2, "muerto"))]
    summary = survival_summary(trees, today=today)
    assert summary.cohorts[3].trees == 2 and summary.cohorts[3].survival_pct == 50.0
    assert summary.cohorts[6].trees == 0


def test_panel_uses_decimal_comma(db, login_as):
    from app.db.models.reforestation import ReforestationProject
    project = ReforestationProject(client_name="Muni")
    db.add(project)
    db.flush()
    db.add_all([ReforestationTree(project_id=project.id, tree_number=n, status=s, date_planted=date(2024, 1, 1))
                for n, s in ((1, "vivo"), (2, "vivo"), (3, "muerto"))])
    db.commit()
    html = login_as("admin").get("/dashboard/reforestacion").text
    assert "66,7 %" in html
    assert "Superv. 3 m" in html
