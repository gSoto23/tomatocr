"""Planilla, phase 2: pay types (hora, día, mensual), the quincena, asesores (ventas) in the
payroll and the employee type in the calendar."""
from datetime import date

import pytest

from app.db.models.payroll import PayrollEntry
from app.db.models.schedule import ProjectSchedule
from app.db.models.user import User
from app.utils.planilla import monthly_share, overtime_rate
from tests.conftest import PASSWORD, make_user


# ---- The quincena -------------------------------------------------------------------------

@pytest.mark.parametrize("start,end,expected", [
    (date(2026, 10, 1), date(2026, 10, 15), 300000),   # first quincena: half
    (date(2026, 10, 16), date(2026, 10, 31), 300000),  # second one, 16 days: still half
    (date(2026, 2, 16), date(2026, 2, 28), 300000),    # February's short second quincena
    (date(2026, 10, 1), date(2026, 10, 31), 600000),   # a whole month
    (date(2026, 10, 16), date(2026, 11, 15), 600000),  # two quincenas across months
])
def test_monthly_salary_pays_half_per_quincena(start, end, expected):
    assert monthly_share(600000, start, end) == pytest.approx(expected)


def test_hired_in_the_middle_of_the_quincena_pays_its_days():
    # Hired on the 10th: 6 of the 15 days of the first quincena.
    assert monthly_share(600000, date(2026, 10, 1), date(2026, 10, 15), hired=date(2026, 10, 10)) == pytest.approx(120000)
    assert monthly_share(600000, date(2026, 10, 1), date(2026, 10, 15), hired=date(2026, 11, 1)) == 0


def test_overtime_rate_falls_back_to_daily_or_monthly():
    assert overtime_rate(User(pay_type="dia", daily_rate=16000, hourly_rate=0)) == 2000
    assert overtime_rate(User(pay_type="mensual", monthly_salary=384000, hourly_rate=0)) == 2000
    assert overtime_rate(User(pay_type="mensual", monthly_salary=384000, hourly_rate=2500)) == 2500


# ---- Generating the payroll ------------------------------------------------------------------

def generate(client, start="2026-10-16", end="2026-10-31"):
    response = client.post("/payroll/generate", json={"start_date": start, "end_date": end})
    assert response.status_code == 200, response.text
    return response.json()["period_id"]


def entry_of(db, user_id):
    return db.query(PayrollEntry).filter(PayrollEntry.user_id == user_id).one_or_none()


def work(db, users, person, day, hours=8.0, overtime=0.0, attendance="asistio"):
    db.add(ProjectSchedule(project_id=users["project_id"], user_id=person.id, date=day, hours_worked=hours,
                           overtime_hours=overtime, is_confirmed=True, attendance=attendance))
    db.commit()


def test_asesor_gets_half_the_salary_without_calendar(db, login_as, users):
    asesor = users["ventas"]
    asesor.pay_type, asesor.monthly_salary, asesor.apply_deductions = "mensual", 600000, True
    db.commit()
    generate(login_as("admin"))
    entry = entry_of(db, asesor.id)
    assert entry.pay_type == "mensual" and entry.gross_salary == 300000
    assert entry.social_charges == round(300000 * 0.0917 / 100) * 100
    assert entry.total_hours == 0 and entry.details == []


def test_monthly_overtime_is_paid_on_top(db, login_as, users):
    supervisor = users["supervisor"]
    supervisor.pay_type, supervisor.monthly_salary, supervisor.hourly_rate = "mensual", 400000, 2000
    db.commit()
    work(db, users, supervisor, date(2026, 10, 20), hours=8, overtime=2)
    generate(login_as("admin"))
    # Half of 400 000, plus 2 h × 2000 × 1.5; the 8 regular hours are already in the salary.
    assert entry_of(db, supervisor.id).gross_salary == 200000 + 6000


def test_daily_pay_counts_confirmed_days(db, login_as, users):
    worker = users["worker"]
    worker.pay_type, worker.daily_rate, worker.hourly_rate = "dia", 20000, 0
    db.commit()
    work(db, users, worker, date(2026, 10, 19))
    work(db, users, worker, date(2026, 10, 20), overtime=1)
    work(db, users, worker, date(2026, 10, 21), hours=0, attendance="no_llego")
    generate(login_as("admin"))
    entry = entry_of(db, worker.id)
    # 2 days × 20 000, plus 1 h extra at (20 000 / 8) × 1.5 = 3750 → 43 750, rounded to hundreds.
    assert entry.pay_type == "dia" and entry.days_worked == 2
    assert entry.gross_salary == round(43750 / 100) * 100 and entry.hourly_rate == 2500


def test_hourly_pay_is_unchanged(db, login_as, users):
    worker = users["worker"]
    worker.hourly_rate = 2000
    db.commit()
    work(db, users, worker, date(2026, 10, 19), hours=8, overtime=2)
    generate(login_as("admin"))
    entry = entry_of(db, worker.id)
    assert entry.pay_type == "hora" and entry.gross_salary == 8 * 2000 + 2 * 2000 * 1.5


@pytest.mark.parametrize("change", [
    {"monthly_salary": 0},                       # nothing to pay
    {"start_date": date(2026, 11, 1)},           # starts after the period
    {"status": "liquidated"},                    # no longer works here
])
def test_who_is_left_out_of_the_monthly_payroll(db, login_as, users, change):
    asesor = users["ventas"]
    asesor.pay_type, asesor.monthly_salary = "mensual", 600000
    for field, value in change.items():
        setattr(asesor, field, value)
    db.commit()
    generate(login_as("admin"))
    assert entry_of(db, asesor.id) is None


# ---- Asesores see their payroll ---------------------------------------------------------------

def test_asesor_sees_only_own_entry(db, login_as, users):
    asesor, worker = users["ventas"], users["worker"]
    asesor.pay_type, asesor.monthly_salary = "mensual", 600000
    worker.hourly_rate = 2000
    db.commit()
    work(db, users, worker, date(2026, 10, 19))
    period_id = generate(login_as("admin"))
    client = login_as("ventas")
    assert client.get("/payroll/").status_code == 200
    detail = client.get(f"/payroll/detail/{period_id}").text
    assert asesor.full_name in detail and worker.full_name not in detail and "Mensual (quincena)" in detail
    report = client.get(f"/payroll/report/{period_id}").text
    assert worker.full_name not in report
    assert client.get("/payments/", follow_redirects=False).headers["location"] == f"/payments/history/{asesor.id}"


@pytest.mark.parametrize("path", ["/payroll/approval", f"/payments/history/1"])
def test_asesor_cannot_see_the_rest(login_as, users, path):
    # users["admin"] is id 1: another person's history.
    assert login_as("ventas").get(path).status_code == 403


def test_asesor_cannot_generate(login_as):
    response = login_as("ventas").post("/payroll/generate", json={"start_date": "2026-10-16", "end_date": "2026-10-31"})
    assert response.status_code == 403


def test_payroll_menu_for_asesor(login_as):
    assert 'href="/payroll"' in login_as("ventas").get("/dashboard/").text


# ---- Employee form ------------------------------------------------------------------------------

def person(**overrides):
    data = {"username": "nuevo", "password": PASSWORD, "full_name": "Nuevo", "role": "worker", "is_active": "true",
            "email": "nuevo@example.com"}
    data.update(overrides)
    return data


def test_form_saves_daily_pay_and_type(db, login_as):
    login_as("admin").post("/users/new", data=person(pay_type="dia", daily_rate="18000", employment_type="ocasional"),
                           follow_redirects=False)
    created = db.query(User).filter(User.username == "nuevo").one()
    assert (created.pay_type, created.daily_rate, created.employment_type) == ("dia", 18000, "ocasional")


def test_asesor_is_always_monthly(db, login_as, users):
    client = login_as("admin")
    client.post("/users/new", data=person(role="ventas", pay_type="hora"), follow_redirects=False)
    assert db.query(User).filter(User.username == "nuevo").one().pay_type == "mensual"
    asesor = users["ventas"]
    client.post(f"/users/{asesor.id}/edit", data=person(username=asesor.username, role="ventas", email="v@example.com"),
                follow_redirects=False)
    db.expire_all()
    assert db.get(User, asesor.id).pay_type == "mensual"


def test_unknown_pay_values_fall_back(db, login_as):
    login_as("admin").post("/users/new", data=person(pay_type="semanal", employment_type="eventual"),
                           follow_redirects=False)
    created = db.query(User).filter(User.username == "nuevo").one()
    assert (created.pay_type, created.employment_type) == ("hora", "fijo")


def test_form_shows_pay_fields(login_as):
    html = login_as("admin").get("/users/new").text
    assert 'name="pay_type"' in html and 'name="daily_rate"' in html and 'name="employment_type"' in html


# ---- Calendar ----------------------------------------------------------------------------------------

def test_calendar_members_carry_their_type(db, login_as, users):
    users["worker"].employment_type = "ocasional"
    db.commit()
    work(db, users, users["worker"], date(2026, 10, 19))
    event = login_as("admin").get("/calendar/events?start=2026-10-19&end=2026-10-26").json()[0]
    assert event["extendedProps"]["members"][0]["employment_type"] == "ocasional"
    assert 'value="type"' in login_as("admin").get("/calendar/").text


def test_labour_cost_follows_the_pay_type(db, login_as, users):
    worker, supervisor = users["worker"], users["supervisor"]
    worker.pay_type, worker.daily_rate, worker.hourly_rate = "dia", 16000, 0
    supervisor.pay_type, supervisor.monthly_salary, supervisor.hourly_rate = "mensual", 384000, 0
    db.commit()
    work(db, users, worker, date(2026, 10, 19), overtime=1)
    # A second project the same day is not a second day's pay.
    db.add(ProjectSchedule(project_id=users["project_id"], user_id=worker.id, date=date(2026, 10, 19), hours_worked=2,
                           is_confirmed=True))
    work(db, users, worker, date(2026, 10, 20), hours=0, attendance="no_llego")
    work(db, users, supervisor, date(2026, 10, 19), hours=4)
    db.commit()
    cost = login_as("admin").get("/calendar/cost?start=2026-10-19&end=2026-10-26").json()
    # Worker: 1 day × 16 000 + 1 h extra × (16 000 / 8) × 1.5 = 19 000. Supervisor: 4 h × 384 000 / 192 = 8000.
    assert cost["cost"] == 27000 and cost["without_rate"] == []
