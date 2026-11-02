"""Planilla, phase 4: lines (bonos, comisiones, ajustes, viáticos, deducciones, adelantos),
fixed viáticos per quincena, adjustments left for the next payroll, and Borrador → Aprobada →
Pagada."""
from datetime import date

import pytest

from app.db.models.payment import PayrollPayment
from app.db.models.payroll import PayrollAdjustment, PayrollEntry, PayrollLine, PayrollPeriod
from app.db.models.schedule import ProjectSchedule
from app.db.models.user import User
from app.utils.planilla import recompute
from tests.conftest import PASSWORD


def generate(client, start="2026-10-16", end="2026-10-31"):
    response = client.post("/payroll/generate", json={"start_date": start, "end_date": end})
    assert response.status_code == 200, response.text
    return response.json()["period_id"]


def entry_of(db, user_id, period_id=None):
    db.expire_all()
    query = db.query(PayrollEntry).filter(PayrollEntry.user_id == user_id)
    if period_id:
        query = query.filter(PayrollEntry.payroll_period_id == period_id)
    return query.one_or_none()


@pytest.fixture
def asesor(db, users):
    person = users["ventas"]
    person.pay_type, person.monthly_salary, person.apply_deductions = "mensual", 600000, True
    db.commit()
    return person


# ---- How each line counts ---------------------------------------------------------------------

def test_recompute_salary_net_and_minus_lines():
    entry = PayrollEntry(base_salary=300000, gross_salary=300000, apply_deductions=True)
    entry.lines = [PayrollLine(kind="bono", amount=50000), PayrollLine(kind="viatico", amount=40000),
                   PayrollLine(kind="adelanto", amount=30000), PayrollLine(kind="deduccion", amount=5000)]
    recompute(entry)
    # Gross 350 000 carries the CCSS (32 095 → 32 100); viáticos add and the rest subtract after.
    assert entry.gross_salary == 350000 and entry.social_charges == 32100
    assert entry.net_salary == 350000 - 32100 + 40000 - 30000 - 5000


def test_negative_adjustment_takes_salary_back():
    entry = PayrollEntry(base_salary=100000, gross_salary=100000, apply_deductions=False)
    entry.lines = [PayrollLine(kind="ajuste", amount=-20000)]
    recompute(entry)
    assert entry.gross_salary == 80000 and entry.net_salary == 80000


# ---- Lines on a draft --------------------------------------------------------------------------------

def test_add_and_remove_a_line_on_a_draft(db, login_as, users, asesor):
    client = login_as("admin")
    generate(client)
    entry = entry_of(db, asesor.id)
    response = client.post(f"/payroll/entry/{entry.id}/lines", json={"kind": "bono", "amount": 50000,
                                                                      "description": "Meta de octubre"})
    assert response.status_code == 200
    entry = entry_of(db, asesor.id)
    assert entry.gross_salary == 350000 and entry.lines[0].description == "Meta de octubre"
    assert client.post(f"/payroll/line/{entry.lines[0].id}/delete").status_code == 200
    entry = entry_of(db, asesor.id)
    assert entry.gross_salary == 300000 and entry.lines == []


@pytest.mark.parametrize("line,problem", [
    ({"kind": "bono", "amount": -100}, "negativos"),
    ({"kind": "regalo", "amount": 100}, "no válido"),
    ({"kind": "viatico", "amount": 0}, "0"),
])
def test_invalid_lines_are_refused(db, login_as, users, asesor, line, problem):
    client = login_as("admin")
    generate(client)
    response = client.post(f"/payroll/entry/{entry_of(db, asesor.id).id}/lines", json=line)
    assert response.status_code == 400 and problem in response.json()["detail"]


def test_an_approved_payroll_takes_no_lines(db, login_as, users, asesor):
    client = login_as("admin")
    period_id = generate(client)
    client.post(f"/payroll/entry/{entry_of(db, asesor.id).id}/lines", json={"kind": "bono", "amount": 1000})
    client.post("/payroll/confirm", json={"period_id": period_id})
    entry = entry_of(db, asesor.id)
    response = client.post(f"/payroll/entry/{entry.id}/lines", json={"kind": "bono", "amount": 1000})
    assert response.status_code == 400 and "ajuste" in response.json()["detail"]
    assert client.post(f"/payroll/line/{entry.lines[0].id}/delete").status_code == 400


@pytest.mark.parametrize("role", ["supervisor", "worker", "ventas"])
def test_only_admin_changes_lines(db, login_as, users, asesor, role):
    generate(login_as("admin"))
    entry = entry_of(db, asesor.id)
    client = login_as(role)
    assert client.post(f"/payroll/entry/{entry.id}/lines", json={"kind": "bono", "amount": 1}).status_code == 403
    assert client.post("/payroll/adjustments", json={"user_id": asesor.id, "kind": "bono",
                                                     "amount": 1}).status_code == 403


# ---- Viáticos per quincena --------------------------------------------------------------------------

def test_fixed_viaticos_come_with_each_quincena(db, login_as, users, asesor):
    asesor.viatico_quincenal = 40000
    db.commit()
    generate(login_as("admin"))
    entry = entry_of(db, asesor.id)
    assert [(l.kind, l.amount) for l in entry.lines] == [("viatico", 40000)]
    # Not salary: the CCSS is the same as without them.
    assert entry.gross_salary == 300000 and entry.net_salary == 300000 - entry.social_charges + 40000


def test_viaticos_alone_make_an_entry(db, login_as, users):
    # A supervisor who sells, with no confirmed hours this quincena: only the viáticos.
    supervisor = users["supervisor"]
    supervisor.also_sells, supervisor.viatico_quincenal = True, 25000
    db.commit()
    generate(login_as("admin"))
    entry = entry_of(db, supervisor.id)
    assert entry.gross_salary == 0 and entry.social_charges == 0 and entry.net_salary == 25000


# ---- Adjustments for the next payroll --------------------------------------------------------------

def test_adjustment_on_an_approved_payroll_goes_to_the_next(db, login_as, users, asesor):
    client = login_as("admin")
    first = generate(client, "2026-10-01", "2026-10-15")
    client.post("/payroll/confirm", json={"period_id": first})
    response = client.post("/payroll/adjustments", json={"user_id": asesor.id, "kind": "ajuste", "amount": -10000,
                                                         "description": "Día no trabajado", "source_period_id": first})
    assert response.status_code == 200
    assert "para la próxima quincena" in client.get("/payroll/").text
    second = generate(client)
    entry = entry_of(db, asesor.id, second)
    assert entry.lines[0].description == f"Día no trabajado (planilla #{first})"
    assert entry.gross_salary == 290000
    assert "para la próxima quincena" not in client.get("/payroll/").text


def test_deleting_the_draft_frees_the_adjustment(db, login_as, users, asesor):
    client = login_as("admin")
    client.post("/payroll/adjustments", json={"user_id": asesor.id, "kind": "bono", "amount": 5000})
    period_id = generate(client)
    adjustment = db.query(PayrollAdjustment).one()
    # Applied: it can't be deleted on its own.
    assert client.post(f"/payroll/adjustments/{adjustment.id}/delete").status_code == 400
    client.delete(f"/payroll/{period_id}")
    db.expire_all()
    assert db.query(PayrollLine).count() == 0
    assert client.post(f"/payroll/adjustments/{adjustment.id}/delete").status_code == 200
    assert db.query(PayrollAdjustment).count() == 0


def test_removing_an_adjustment_line_leaves_it_pending(db, login_as, users, asesor):
    client = login_as("admin")
    client.post("/payroll/adjustments", json={"user_id": asesor.id, "kind": "bono", "amount": 5000})
    generate(client)
    line = entry_of(db, asesor.id).lines[0]
    response = client.post(f"/payroll/line/{line.id}/delete")
    assert "pendiente" in response.json()["message"]
    assert "para la próxima quincena" in client.get("/payroll/").text


# ---- Borrador → Aprobada → Pagada ----------------------------------------------------------------------

def test_payroll_becomes_paid_when_everyone_has_a_payment(db, login_as, users, asesor):
    worker = users["worker"]
    worker.hourly_rate = 2000
    db.add(ProjectSchedule(project_id=users["project_id"], user_id=worker.id, date=date(2026, 10, 19),
                           hours_worked=8, is_confirmed=True))
    db.commit()
    client = login_as("admin")
    period_id = generate(client)
    assert "Borrador" in client.get(f"/payroll/detail/{period_id}").text
    client.post("/payroll/confirm", json={"period_id": period_id})
    db.add(PayrollPayment(user_id=asesor.id, amount=1, date=date(2026, 10, 31), payroll_period_id=period_id))
    db.commit()
    page = client.get(f"/payroll/detail/{period_id}").text
    assert "Aprobada" in page and "1 de 2 pagados" in page
    db.add(PayrollPayment(user_id=worker.id, amount=1, date=date(2026, 10, 31), payroll_period_id=period_id))
    db.commit()
    assert "Pagada" in client.get("/payroll/").text


def test_person_sees_own_lines(db, login_as, users, asesor):
    client = login_as("admin")
    period_id = generate(client)
    client.post(f"/payroll/entry/{entry_of(db, asesor.id).id}/lines",
                json={"kind": "adelanto", "amount": 20000, "description": "Adelanto del 20/10"})
    client.post("/payroll/confirm", json={"period_id": period_id})
    page = login_as("ventas").get(f"/payroll/detail/{period_id}").text
    assert "Adelanto del 20/10" in page and "Comprobante de pago" in page


# ---- Employee form ----------------------------------------------------------------------------------------

def test_form_saves_the_viaticos(db, login_as):
    login_as("admin").post("/users/new", data={"username": "nuevo", "password": PASSWORD, "full_name": "Nuevo",
                                               "role": "ventas", "is_active": "true", "email": "n@example.com",
                                               "viatico_quincenal": "35000"}, follow_redirects=False)
    assert db.query(User).filter(User.username == "nuevo").one().viatico_quincenal == 35000


# ---- The net never goes below zero ------------------------------------------------------------------

def test_a_line_that_leaves_a_negative_net_is_refused(db, login_as, users, asesor):
    client = login_as("admin")
    generate(client)
    entry = entry_of(db, asesor.id)
    response = client.post(f"/payroll/entry/{entry.id}/lines", json={"kind": "adelanto", "amount": 400000})
    assert response.status_code == 400 and "negativo" in response.json()["detail"]
    entry = entry_of(db, asesor.id)
    assert entry.lines == [] and entry.net_salary > 0


def test_negative_adjustment_waits_for_a_payroll_with_salary(db, login_as, users):
    worker = users["worker"]
    worker.hourly_rate = 2000
    db.commit()
    client = login_as("admin")
    client.post("/payroll/adjustments", json={"user_id": worker.id, "kind": "ajuste", "amount": -5000,
                                              "description": "Pagado de más"})
    # No hours this quincena: nothing to take it from, so no entry and the adjustment stays pending.
    generate(client, "2026-11-01", "2026-11-15")
    assert entry_of(db, worker.id) is None
    assert "para la próxima quincena" in client.get("/payroll/").text
    # With hours, it applies.
    db.add(ProjectSchedule(project_id=users["project_id"], user_id=worker.id, date=date(2026, 11, 17),
                           hours_worked=8, is_confirmed=True))
    db.commit()
    generate(client, "2026-11-16", "2026-11-30")
    entry = entry_of(db, worker.id)
    assert entry.gross_salary == 16000 - 5000 and entry.lines[0].kind == "ajuste"
