"""UX round 2b (docs/PUNTOS_DIFICILES_UX.md, priority B): budgets, payroll and payments,
the calendar and reforestation."""
from datetime import date, timedelta

import pytest

from app.db.models.activity import ActivityLog
from app.db.models.finance import BudgetLine, Invoice, InvoiceStatus, Payment, ProjectBudget, ProjectCost
from app.db.models.payment import PayrollPayment
from app.db.models.payroll import PayrollEntry, PayrollPeriod
from app.db.models.project_details import ProjectLocation
from app.db.models.reforestation import ReforestationProject, ReforestationTree, TreeCheck
from app.db.models.schedule import ProjectSchedule
from app.db.models.user import User
from app.utils.reforestation import record_check

# --- Budgets --------------------------------------------------------------------------------


@pytest.fixture
def budget(db, users):
    b = ProjectBudget(project_id=users["project_id"], licitation_number="LIC-1")
    db.add(b)
    db.flush()
    line = BudgetLine(budget_id=b.id, name="Mantenimiento", subtotal=1000, tax_percentage=0)
    db.add(line)
    db.flush()
    paid = Invoice(budget_id=b.id, budget_line_id=line.id, invoice_number="FE-1", amount=600,
                   issue_date=date.today(), due_date=date.today() + timedelta(days=30), status=InvoiceStatus.PAID)
    db.add(paid)
    db.flush()
    db.add(Payment(invoice_id=paid.id, payment_date=date.today(), deposit_number="D1", amount=588,
                   retention_amount=12))
    db.add(ProjectCost(project_id=users["project_id"], date=date.today(), description="Abono secreto", amount=99))
    db.commit()
    return {"budget": b, "line": line, "paid": paid}


def test_client_sees_invoices_and_payments_only(login_as, users, budget):
    html = login_as("client").get(f"/finance/{users['project_id']}").text
    assert "FE-1" in html and "Por cobrar" in html and "Por facturar" in html
    for internal in ("Abono secreto", "Ganancia", "Planillas Cargadas", "Retenciones Institucionales", "Gastos Registrados"):
        assert internal not in html, internal
    listing = login_as("client").get("/finance/").text
    assert "Costos" not in listing and "Por cobrar" in listing


def test_admin_sees_everything_with_clear_names(login_as, users, budget):
    html = login_as("admin").get(f"/finance/{users['project_id']}").text
    assert "Abono secreto" in html and "Ganancia" in html and "Presupuesto del proyecto" in html
    assert "queda por facturar: ₡400.00" in html and "Registrar pago" not in html  # FE-1 is paid
    assert "Gestión Financiera" not in login_as("admin").get("/finance/").text


def invoice_form(amount, **extra):
    data = {"invoice_number": "FE-2", "issue_date": date.today().isoformat(),
            "due_date": (date.today() + timedelta(days=30)).isoformat(), "amount": amount}
    data.update(extra)
    return data


def test_invoicing_over_the_line_needs_confirmation(db, login_as, users, budget):
    client = login_as("admin")
    url = f"/finance/{users['project_id']}/invoice"
    over = client.post(url, data=invoice_form(500, budget_line_id=budget["line"].id), follow_redirects=False)
    assert over.status_code == 303 and over.cookies.get("toast_type") == "error"
    assert db.query(Invoice).count() == 1
    ok = client.post(url, data=invoice_form(500, budget_line_id=budget["line"].id, confirm_over="true"),
                     follow_redirects=False)
    assert ok.status_code == 303 and db.query(Invoice).count() == 2


def test_invoice_with_payment_is_not_deleted(db, login_as, budget):
    response = login_as("admin").post(f"/finance/invoice/{budget['paid'].id}/delete", follow_redirects=False)
    assert response.status_code == 303
    assert db.query(Invoice).count() == 1


# --- Payroll --------------------------------------------------------------------------------

def test_payroll_keeps_the_rate_it_was_generated_with(db, login_as, users):
    worker = db.get(User, users["worker"].id)
    worker.hourly_rate = 1000
    day = date(2026, 9, 3)
    db.add(ProjectSchedule(project_id=users["project_id"], user_id=worker.id, date=day, hours_worked=8,
                           overtime_hours=2, is_confirmed=True))
    db.commit()
    client = login_as("admin")
    period_id = client.post("/payroll/generate", json={"start_date": "2026-09-01", "end_date": "2026-09-15"}).json()["period_id"]
    entry = db.query(PayrollEntry).filter_by(payroll_period_id=period_id).one()
    assert entry.hourly_rate == 1000
    worker.hourly_rate = 5000
    db.commit()
    detail = client.get(f"/payroll/detail/{period_id}").text
    report = client.get(f"/payroll/report/{period_id}").text
    assert "₡3,000.00" in detail and "₡3,000.00" in report  # 2 h x 1000 x 1.5
    assert 'colspan="6"' in report


def test_approval_confirms_only_pending(login_as):
    html = login_as("admin").get("/payroll/approval").text
    assert "Confirmar pendientes" in html and "data-confirmed" in html


@pytest.fixture
def final_period(db, users):
    p = PayrollPeriod(start_date=date(2026, 9, 1), end_date=date(2026, 9, 15), status="final")
    db.add(p)
    db.flush()
    db.add(PayrollEntry(payroll_period_id=p.id, user_id=users["worker"].id, total_hours=80, gross_salary=200000,
                        social_charges=18300, net_salary=181700, hourly_rate=2500))
    db.commit()
    return p


def test_payment_keeps_method_reference_and_payroll(db, login_as, users, final_period):
    client = login_as("admin")
    page = client.get(f"/payments/history/{users['worker'].id}").text
    assert "Planilla que paga" in page and "181,700.00" in page
    client.post("/payments/create", data={"user_id": users["worker"].id, "amount": 181700, "hours_paid": 80,
                                          "date": "2026-09-16", "method": "Sinpe", "reference": " 12345 ",
                                          "payroll_period_id": final_period.id}, follow_redirects=False)
    payment = db.query(PayrollPayment).one()
    assert (payment.method, payment.reference, payment.payroll_period_id) == ("Sinpe", "12345", final_period.id)
    worker_view = login_as("worker").get(f"/payments/history/{users['worker'].id}").text
    assert "Ref. 12345" in worker_view and "Sinpe" in worker_view


def test_workers_and_supervisors_reach_their_payments(login_as, users):
    assert f"/payments/history/{users['worker'].id}" in login_as("worker").get("/payroll/").text
    response = login_as("supervisor").get("/payments/", follow_redirects=False)
    assert response.headers["location"] == f"/payments/history/{users['supervisor'].id}"


# --- Calendar -------------------------------------------------------------------------------

def assign(client, users, start, end=None, **extra):
    data = {"project_id": users["project_id"], "user_id": users["worker"].id, "date": start}
    if end:
        data["end_date"] = end
    data.update(extra)
    return client.post("/calendar/schedule", data=data)


def test_range_skips_sunday_unless_asked(db, login_as, users):
    client = login_as("supervisor")
    # 2026-09-21 is a Monday: Monday to Sunday
    assert assign(client, users, "2026-09-21", "2026-09-27").status_code == 200
    days = sorted(s.date.weekday() for s in db.query(ProjectSchedule))
    assert days == [0, 1, 2, 3, 4, 5]
    assert assign(client, users, "2026-10-03", "2026-10-04", include_sunday="true", include_saturday="false",
                  confirm_conflicts="true").status_code == 200
    assert db.query(ProjectSchedule).filter(ProjectSchedule.date == date(2026, 10, 4)).count() == 1
    assert db.query(ProjectSchedule).filter(ProjectSchedule.date == date(2026, 10, 3)).count() == 0


def test_double_assignment_asks_first(db, login_as, users):
    client = login_as("admin")
    assert assign(client, users, "2026-09-22").status_code == 200
    again = assign(client, users, "2026-09-22")
    assert again.status_code == 409 and "Ya tiene asignación" in again.json()["message"]
    assert assign(client, users, "2026-09-22", confirm_conflicts="true").status_code == 200
    assert db.query(ProjectSchedule).count() == 2


def test_assignment_keeps_sede_and_hours(db, login_as, users):
    sede = ProjectLocation(project_id=users["project_id"], name="Torre A")
    db.add(sede)
    db.commit()
    assert assign(login_as("admin"), users, "2026-09-23", location_id=sede.id, hours=6).status_code == 200
    s = db.query(ProjectSchedule).one()
    assert (s.location_id, s.hours_worked) == (sede.id, 6)
    event = login_as("admin").get("/calendar/events?start=2026-09-01&end=2026-09-30").json()[0]
    assert event["extendedProps"]["members"][0]["location_name"] == "Torre A"


def test_calendar_lists_only_active_people(db, login_as, users):
    worker = db.get(User, users["worker"].id)
    worker.full_name = "Persona Inactiva"
    worker.is_active = False
    db.commit()
    assert "Persona Inactiva" not in login_as("admin").get("/calendar/").text


# --- Reforestation --------------------------------------------------------------------------

@pytest.fixture
def forest(db, users):
    project = ReforestationProject(client_name="Municipalidad de Alajuela", project_id=users["project_id"])
    db.add(project)
    db.flush()
    trees = [ReforestationTree(project_id=project.id, tree_number=n) for n in (1, 2)]
    db.add_all(trees)
    db.flush()
    record_check(trees[0], date(2026, 9, 1), "vivo")
    record_check(trees[0], date(2026, 9, 10), "muerto")
    db.commit()
    return project


def monitor(client, users, **data):
    form = {"checked_at": date.today().isoformat(), "mode": "numbers", "tree_numbers": "2", "status": "vivo"}
    form.update(data)
    return client.post(f"/projects/{users['project_id']}/monitoreo", data=form, follow_redirects=False)


def test_bad_height_and_photo_say_why_in_spanish(db, login_as, users, forest):
    client = login_as("worker")
    assert "la altura tiene que ser un n" in monitor(client, users, height_cm="alto").cookies["toast_message"]
    photo = client.post(f"/projects/{users['project_id']}/monitoreo",
                        data={"checked_at": date.today().isoformat(), "mode": "numbers", "tree_numbers": "2",
                              "status": "vivo"},
                        files={"photo": ("nota.txt", b"hola", "text/plain")}, follow_redirects=False)
    assert photo.status_code == 303 and "no es una foto" in photo.cookies["toast_message"]
    assert db.query(TreeCheck).count() == 2


def test_supervisor_removes_a_wrong_check_and_the_tree_goes_back(db, login_as, users, forest):
    latest = db.query(TreeCheck).filter_by(status="muerto").one()
    assert login_as("worker").post(f"/projects/{users['project_id']}/monitoreo/{latest.id}/delete",
                                   follow_redirects=False).status_code == 403
    client = login_as("supervisor")
    assert "Últimos monitoreos" in client.get(f"/projects/{users['project_id']}/monitoreo").text
    client.post(f"/projects/{users['project_id']}/monitoreo/{latest.id}/delete", follow_redirects=False)
    db.expire_all()
    tree = db.query(ReforestationTree).filter_by(tree_number=1).one()
    assert (tree.status, tree.last_checked_at) == ("vivo", date(2026, 9, 1))


def test_admin_deletes_a_tree_renames_and_deletes_the_project(db, login_as, users, forest):
    client = login_as("admin")
    client.post(f"/dashboard/reforestacion/{forest.id}/trees/delete", data={"tree_number": "1"})
    assert db.query(ReforestationTree).count() == 1 and db.query(TreeCheck).count() == 0
    client.post(f"/dashboard/reforestacion/{forest.id}/rename", data={"client_name": "Muni Alajuela"})
    db.expire_all()
    assert db.get(ReforestationProject, forest.id).client_name == "Muni Alajuela"
    client.post(f"/dashboard/reforestacion/{forest.id}/delete", data={"confirm_name": "otra cosa"})
    assert db.query(ReforestationProject).count() == 1
    client.post(f"/dashboard/reforestacion/{forest.id}/delete", data={"confirm_name": "muni alajuela"})
    assert db.query(ReforestationProject).count() == 0 and db.query(ReforestationTree).count() == 0
    assert db.query(ActivityLog).filter(ActivityLog.entity_type == "REFORESTATION").count() == 3


def test_supervisor_cannot_delete_trees(login_as, forest):
    response = login_as("supervisor").post(f"/dashboard/reforestacion/{forest.id}/trees/delete",
                                           data={"tree_number": "1"})
    assert response.status_code == 403


def test_import_with_a_differently_typed_name_updates_the_same_project(db, login_as, forest):
    csv = "TreeNumber,Species\n3,Roble\n"
    response = login_as("admin").post("/dashboard/reforestacion/upload-csv", data={"client_name": "municipalidad  de ALAJUELA"},
                                      files={"file": ("datos.csv", csv.encode(), "text/csv")})
    assert response.status_code == 200, response.text
    assert db.query(ReforestationProject).count() == 1 and db.query(ReforestationTree).count() == 3
