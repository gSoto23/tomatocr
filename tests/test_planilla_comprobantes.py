"""Planilla, phase 6 and the clearer Planilla screens: payslips, Excel, the payment list, paying
from the quincena, drafts hidden from people, and the lists of Pagos and Liquidaciones."""
import io
from datetime import date

import pytest

from app.db.models.payment import PayrollPayment
from app.db.models.payroll import PayrollEntry
from app.db.models.schedule import ProjectSchedule
from app.utils.planilla_resumen import period_label


@pytest.fixture
def quincena(db, login_as, users):
    """Admin client and a draft quincena with the asesor (monthly + viáticos) and a worker by the hour."""
    asesor, worker = users["ventas"], users["worker"]
    asesor.pay_type, asesor.monthly_salary, asesor.viatico_quincenal = "mensual", 600000, 40000
    asesor.full_name, worker.full_name = "Diego Rojas", "Andrés Solano"
    worker.hourly_rate, worker.payment_method, worker.account_number = 2000, "Sinpe", "8888-0000"
    db.add(ProjectSchedule(project_id=users["project_id"], user_id=worker.id, date=date(2026, 10, 19),
                           hours_worked=8, overtime_hours=1, is_confirmed=True))
    db.commit()
    client = login_as("admin")
    period_id = client.post("/payroll/generate", json={"start_date": "2026-10-16", "end_date": "2026-10-31"}).json()["period_id"]
    entries = {e.user_id: e for e in db.query(PayrollEntry)}
    return {"client": client, "period": period_id, "asesor": entries[asesor.id], "worker": entries[worker.id]}


def approve(q):
    assert q["client"].post("/payroll/confirm", json={"period_id": q["period"]}).status_code == 200


def test_period_label_reads_like_people_say_it():
    class P:
        pass
    p = P()
    p.start_date, p.end_date = date(2026, 10, 16), date(2026, 10, 31)
    assert period_label(p) == "16–31 oct 2026"
    p.start_date, p.end_date = date(2026, 10, 16), date(2026, 11, 15)
    assert period_label(p) == "16 oct – 15 nov 2026"


# ---- Detail -------------------------------------------------------------------------------------------

def test_detail_shows_quincena_net_and_actions(quincena):
    page = quincena["client"].get(f"/payroll/detail/{quincena['period']}").text
    assert "Quincena 16–31 oct 2026" in page and "Neto a pagar" in page and "Aprobar quincena" in page
    assert f'/payroll/{quincena["period"]}/excel' in page and f'/payroll/{quincena["period"]}/comprobantes' in page
    assert "Diego Rojas" in page and "Andrés Solano" in page


# ---- Payslips ------------------------------------------------------------------------------------------

def test_payslip_breaks_down_the_pay(quincena):
    page = quincena["client"].get(f"/payroll/{quincena['period']}/comprobante/{quincena['asesor'].id}").text
    assert "Comprobante de pago" in page and "Diego Rojas" in page
    assert "₡300,000.00" in page and "Viáticos" in page and "₡40,000.00" in page
    assert "window.print()" in page and "window.onload" not in page  # prints on request only


def test_all_payslips_one_per_page(quincena):
    page = quincena["client"].get(f"/payroll/{quincena['period']}/comprobantes").text
    assert page.count("Comprobante de pago") == 2 and "page-break" in page


def test_person_sees_own_payslip_only_once_approved(quincena, login_as):
    worker = login_as("worker")
    assert worker.get(f"/payroll/detail/{quincena['period']}").status_code == 404
    assert worker.get(f"/payroll/{quincena['period']}/comprobante/{quincena['worker'].id}").status_code == 404
    assert "Quincena 16–31 oct 2026" not in worker.get("/payroll/").text
    approve(quincena)
    page = worker.get(f"/payroll/detail/{quincena['period']}").text
    assert "Comprobante de pago" in page and "Andrés Solano" in page and "Diego Rojas" not in page
    assert worker.get(f"/payroll/{quincena['period']}/comprobante/{quincena['asesor'].id}").status_code == 404
    assert worker.get(f"/payroll/{quincena['period']}/comprobantes").status_code == 403


def test_payment_list_has_no_auto_print(quincena):
    page = quincena["client"].get(f"/payroll/report/{quincena['period']}").text
    assert "Listado de pago" in page and "8888-0000" in page and "window.onload" not in page


# ---- Excel -----------------------------------------------------------------------------------------------

def test_excel_has_summary_lines_and_days(quincena):
    from openpyxl import load_workbook
    response = quincena["client"].get(f"/payroll/{quincena['period']}/excel")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/vnd.openxmlformats")
    assert "attachment" in response.headers["content-disposition"]
    book = load_workbook(io.BytesIO(response.content))
    assert book.sheetnames == ["Resumen", "Líneas", "Días"]
    rows = [r for r in book["Resumen"].iter_rows(values_only=True) if r and r[0]]
    people = {r[0]: r for r in rows}
    assert people["Diego Rojas"][9] == 40000  # viáticos column
    assert people["Total"][11] == quincena["asesor"].net_salary + quincena["worker"].net_salary
    assert any(r and r[1] == "Viáticos" for r in book["Líneas"].iter_rows(values_only=True))
    assert any(r and r[0] == "Andrés Solano" and r[3] == 8 for r in book["Días"].iter_rows(values_only=True))


@pytest.mark.parametrize("role", ["supervisor", "worker", "ventas"])
def test_only_admin_downloads_excel(quincena, login_as, role):
    approve(quincena)
    assert login_as(role).get(f"/payroll/{quincena['period']}/excel").status_code == 403


# ---- Paying from the quincena ----------------------------------------------------------------------------

def pay(q, entry, **extra):
    body = {"date": "2026-10-31", "method": "Sinpe", "reference": "S-1", **extra}
    return q["client"].post(f"/payroll/entry/{entry.id}/pay", json=body)


def test_pay_from_the_quincena_records_the_net(db, quincena):
    assert pay(quincena, quincena["worker"]).status_code == 400  # draft: approve first
    approve(quincena)
    response = pay(quincena, quincena["worker"])
    assert response.status_code == 200
    payment = db.query(PayrollPayment).one()
    assert payment.amount == quincena["worker"].net_salary and payment.payroll_period_id == quincena["period"]
    assert payment.method == "Sinpe" and payment.reference == "S-1"
    # Once only, and the quincena counts it.
    assert pay(quincena, quincena["worker"]).status_code == 400
    assert "1 de 2 pagados" in quincena["client"].get(f"/payroll/detail/{quincena['period']}").text


def test_pay_needs_a_method(quincena):
    approve(quincena)
    assert pay(quincena, quincena["worker"], method="Cheque").status_code == 400


# ---- What to do next and the lists ------------------------------------------------------------------------

def test_index_says_what_comes_next(db, quincena, users):
    db.add(ProjectSchedule(project_id=users["project_id"], user_id=users["worker"].id, date=date(2026, 10, 20),
                           hours_worked=8, is_confirmed=False))
    db.commit()
    page = quincena["client"].get("/payroll/").text
    assert "1 día por confirmar" in page and "16–31 oct 2026 en borrador" in page
    approve(quincena)
    page = quincena["client"].get("/payroll/").text
    assert "2 por pagar" in page and "Generar quincena" in page


def test_approval_cards_count_pending_days(db, login_as, users):
    db.add(ProjectSchedule(project_id=users["project_id"], user_id=users["worker"].id, date=date(2026, 10, 20),
                           hours_worked=8, is_confirmed=False))
    db.commit()
    page = login_as("admin").get("/payroll/approval").text
    assert f'"{users["project_id"]}": 1' in page and "Quincena anterior" in page


def test_pagos_and_liquidaciones_list_everyone_in_spanish(db, login_as, users):
    users["ventas"].full_name = "Diego Rojas"
    db.commit()
    client = login_as("admin")
    pagos = client.get("/payments/").text
    liquidaciones = client.get("/liquidation/").text
    assert "Diego Rojas" in pagos and "Ventas" in pagos and "Sin pagos registrados" in pagos
    assert "Diego Rojas" in liquidaciones and "Trabajador" in liquidaciones and ">worker<" not in liquidaciones


def test_planilla_tabs_on_every_part(login_as):
    client = login_as("admin")
    for path in ("/payroll/", "/payroll/approval", "/payments/", "/payroll/commissions", "/liquidation/"):
        page = client.get(path).text
        assert 'aria-label="Planilla"' in page and 'aria-current="page"' in page, path
