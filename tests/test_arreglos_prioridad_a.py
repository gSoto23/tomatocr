"""Priority-A fixes found while writing the manual (docs/PUNTOS_DIFICILES_UX.md):
partial payments add up, "+ Agregar Costo" starts empty, "Apl. Ded?" works, payrolls
can't overlap, and editing a calendar assignment keeps the ticked tasks."""
import json
from datetime import date

import pytest

from app.db.models.finance import BudgetLine, Invoice, InvoiceStatus, ProjectBudget
from app.db.models.payroll import PayrollEntry, PayrollPeriod
from app.db.models.schedule import ProjectSchedule, ScheduleTask
from app.db.models.user import User

TODAY = date(2026, 9, 27)


@pytest.fixture
def invoice(db, users):
    budget = ProjectBudget(project_id=users["project_id"])
    db.add(budget)
    db.flush()
    line = BudgetLine(budget_id=budget.id, name="Mantenimiento", subtotal=1000000, tax_percentage=13)
    db.add(line)
    db.flush()
    inv = Invoice(budget_id=budget.id, budget_line_id=line.id, invoice_number="FE-1", issue_date=TODAY,
                  due_date=TODAY, amount=100000)
    db.add(inv)
    db.commit()
    return inv


def pay(client, inv, amount, receipt, kind="partial", retention=0, note="abono"):
    return client.post(f"/finance/invoice/{inv.id}/pay", data={
        "payment_date": "2026-09-20" if receipt == "D-1" else "2026-09-27", "deposit_number": receipt,
        "amount": amount, "retention_amount": retention, "payment_type": kind, "note": note}, follow_redirects=False)


def test_partial_payments_add_up(db, login_as, invoice):
    client = login_as("admin")
    assert pay(client, invoice, 40000, "D-1", note="primer abono").status_code == 303
    assert pay(client, invoice, 58000, "D-2", kind="full", retention=2000, note="cancelación").status_code == 303
    db.expire_all()
    inv = db.get(Invoice, invoice.id)
    assert inv.status == InvoiceStatus.PAID
    assert (inv.payment.amount, inv.payment.retention_amount) == (98000, 2000)
    assert inv.payment.deposit_number == "D-1, D-2" and inv.payment.payment_date == date(2026, 9, 27)
    assert "20/09/2026: primer abono" in inv.note and "27/09/2026: cancelación" in inv.note


def test_pay_window_proposes_what_is_still_owed(db, login_as, invoice):
    client = login_as("admin")
    pay(client, invoice, 40000, "D-1")
    html = client.get(f"/finance/{db.get(Invoice, invoice.id).budget.project_id}").text
    assert f"openPayModal({invoice.id}, \"FE-1\", 100000.0, 40000.0)" in html.replace("&#34;", '"')


def test_add_cost_button_starts_an_empty_form(login_as, invoice, users):
    html = login_as("admin").get(f"/finance/{users['project_id']}").text
    assert '@click="openCostModal()"' in html and '@click="showCostModal = true"' not in html


# --- Payroll -----------------------------------------------------------------------------

@pytest.fixture
def period(db, users):
    p = PayrollPeriod(start_date=date(2026, 9, 1), end_date=date(2026, 9, 15), status="draft")
    db.add(p)
    db.flush()
    entry = PayrollEntry(payroll_period_id=p.id, user_id=users["worker"].id, total_hours=80, gross_salary=200000,
                         social_charges=18300, net_salary=181700, apply_deductions=True)
    db.add(entry)
    db.commit()
    return p, entry


def test_deductions_checkbox_works(db, login_as, period):
    p, entry = period
    client = login_as("admin")
    assert f"toggleDeductions({entry.id}, this.checked" in client.get(f"/payroll/detail/{p.id}").text
    response = client.patch(f"/payroll/entry/{entry.id}", json={"apply_deductions": False})
    assert response.status_code == 200
    db.expire_all()
    assert db.get(PayrollEntry, entry.id).net_salary == 200000


def test_final_payroll_cannot_change(db, login_as, period):
    p, entry = period
    p.status = "final"
    db.commit()
    client = login_as("admin")
    assert client.patch(f"/payroll/entry/{entry.id}", json={"apply_deductions": False}).status_code == 400
    assert "disabled" in client.get(f"/payroll/detail/{p.id}").text


@pytest.mark.parametrize("start,end,ok", [
    ("2026-09-10", "2026-09-20", False),   # overlaps 1–15
    ("2026-08-20", "2026-09-01", False),   # touches the first day
    ("2026-09-16", "2026-09-30", True),
    ("2026-09-30", "2026-09-16", False),   # end before start
])
def test_payrolls_cannot_overlap(db, login_as, period, start, end, ok):
    response = login_as("admin").post("/payroll/generate", json={"start_date": start, "end_date": end})
    assert (response.status_code == 200) == ok, response.text
    if not ok:
        assert "planilla #" in response.json()["detail"] or "anterior" in response.json()["detail"]


# --- Calendar ----------------------------------------------------------------------------

@pytest.fixture
def assignment(db, users):
    s = ProjectSchedule(project_id=users["project_id"], user_id=users["worker"].id, date=TODAY)
    db.add(s)
    db.flush()
    done = ScheduleTask(schedule_id=s.id, title="Corta", description="Zacate", completed=True)
    other = ScheduleTask(schedule_id=s.id, title="Poda", description="Setos")
    db.add_all([done, other])
    db.commit()
    return s, done, other


def edit(client, schedule, tasks):
    return client.post(f"/calendar/schedule/{schedule.id}/edit", data={
        "project_id": schedule.project_id, "user_id": schedule.user_id, "date": TODAY.isoformat(),
        "tasks_json": json.dumps(tasks)})


def test_editing_keeps_ticked_tasks(db, login_as, assignment):
    s, done, other = assignment
    ids = (done.id, other.id)
    response = edit(login_as("supervisor"), s, [
        {"id": ids[0], "title": "Corta", "description": "Zacate y orillas"},   # edited, stays ticked
        {"title": "Riego", "description": ""},                                  # new
    ])
    assert response.status_code == 200
    db.expire_all()
    tasks = {t.title: t for t in db.query(ScheduleTask).filter_by(schedule_id=s.id)}
    assert set(tasks) == {"Corta", "Riego"}                                    # "Poda" removed
    assert tasks["Corta"].id == ids[0] and tasks["Corta"].completed and tasks["Corta"].description == "Zacate y orillas"
    assert not tasks["Riego"].completed


def test_editing_without_ids_matches_by_text(db, login_as, assignment):
    s, done, _ = assignment
    done_id = done.id
    edit(login_as("admin"), s, [{"title": "Corta", "description": "Zacate"}, {"title": "Poda", "description": "Setos"}])
    db.expire_all()
    assert db.get(ScheduleTask, done_id).completed
