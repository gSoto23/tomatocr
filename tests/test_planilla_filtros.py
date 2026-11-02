"""Planilla filters (Comisiones, Quincenas, the quincena detail, Pagos, Liquidaciones) and
commission tiers: an invoice under the threshold earns one %, one at or above it another."""
from datetime import date

import pytest

from app.db.models.commission import Commission
from app.db.models.crm import Account, Opportunity
from app.db.models.finance import BudgetLine, Invoice, ProjectBudget
from app.db.models.payroll import PayrollPeriod
from app.db.models.project import Project
from app.utils.comisiones import percent_for, set_general_rules
from tests.conftest import make_user


# ---- Comisiones: the filter that broke and the payment dates ------------------------------------

def test_commissions_filter_with_todos_does_not_break(login_as):
    # "Todos" sends persona= (empty): it means no filter, not an error.
    response = login_as("admin").get("/payroll/commissions?persona=&estado=")
    assert response.status_code == 200 and "Reglas generales" in response.text
    assert login_as("admin").get("/payroll/commissions?persona=abc&desde=nope").status_code == 200


def test_commissions_filter_by_payment_dates(db, login_as, users):
    seller = users["ventas"]
    db.add_all([Commission(user_id=seller.id, kind="factura", amount=1000, client_name="Octubre",
                           payment_date=date(2026, 10, 10)),
                Commission(user_id=seller.id, kind="factura", amount=2000, client_name="Noviembre",
                           payment_date=date(2026, 11, 2))])
    db.commit()
    for role in ("admin", "ventas"):
        page = login_as(role).get("/payroll/commissions?desde=2026-11-01&hasta=2026-11-30").text
        assert "Noviembre" in page and "Octubre" not in page and "₡2,000.00" in page


# ---- Tiers -----------------------------------------------------------------------------------------

@pytest.mark.parametrize("base,expected", [(999999, 3), (1000000, 5), (2500000, 5)])
def test_tier_picks_the_percent_for_the_whole_invoice(base, expected):
    rules = {"percent": 3, "percent_high": 5, "threshold": 1000000}
    assert percent_for(rules, base) == expected


def test_without_threshold_one_percent():
    assert percent_for({"percent": 4, "percent_high": 9, "threshold": 0}, 5000000) == 4


@pytest.fixture
def invoices(db, users):
    """Two invoices of the asesor's Nuevo opportunity: ₡565,000 and ₡1,695,000 (₡500k and ₡1.5M + 13% IVA)."""
    seller = users["ventas"]
    account = Account(name="Hotel Arenal", owner_id=seller.id)
    db.add(account)
    db.flush()
    opportunity = Opportunity(account_id=account.id, title="Jardines", kind="renovacion", stage="ganado", owner_id=seller.id)
    db.add(opportunity)
    db.flush()
    project = db.get(Project, users["project_id"])
    project.account_id, project.opportunity_id = account.id, opportunity.id
    budget = ProjectBudget(project_id=project.id)
    db.add(budget)
    db.flush()
    line = BudgetLine(budget_id=budget.id, name="Mantenimiento", subtotal=5000000, tax_percentage=13)
    db.add(line)
    db.flush()
    found = [Invoice(budget_id=budget.id, budget_line_id=line.id, invoice_number=f"FE-{n}", issue_date=date(2026, 11, 1),
                     due_date=date(2026, 11, 1), amount=amount) for n, amount in ((1, 565000), (2, 1695000))]
    db.add_all(found)
    set_general_rules(db, 3, 0, 1000000, 5)
    db.commit()
    return found


def pay(client, invoice):
    return client.post(f"/finance/invoice/{invoice.id}/pay", data={
        "payment_date": "2026-11-02", "deposit_number": f"D-{invoice.id}", "amount": invoice.amount,
        "retention_amount": 0, "payment_type": "full", "note": ""}, follow_redirects=False)


def test_paid_invoices_use_their_tier(db, login_as, invoices):
    client = login_as("admin")
    for invoice in invoices:
        pay(client, invoice)
    db.expire_all()
    found = {c.invoice_number: c for c in db.query(Commission)}
    assert (found["FE-1"].rate, found["FE-1"].amount) == (3, 15000)   # ₡500,000 × 3 %
    assert (found["FE-2"].rate, found["FE-2"].amount) == (5, 75000)   # ₡1,500,000 × 5 %


def test_own_tiers_win_field_by_field(db, login_as, users, invoices):
    seller = users["ventas"]
    seller.commission_threshold = 400000      # own threshold; the two % stay the general ones
    db.commit()
    pay(login_as("admin"), invoices[0])
    db.expire_all()
    assert db.query(Commission).one().rate == 5


def test_rules_and_employee_form_save_the_tiers(db, login_as, users):
    client = login_as("admin")
    client.post("/payroll/commissions/settings", data={"percent": "3", "percent_high": "5", "threshold": "1000000",
                                                       "new_client": "0"})
    page = client.get("/payroll/commissions").text
    assert 'value="1000000.00"' in page and "desde ₡1,000,000" in page
    seller = users["ventas"]
    client.post(f"/users/{seller.id}/edit", data={"username": seller.username, "full_name": "Asesor", "role": "ventas",
                                                  "email": "v@example.com", "is_active": "true",
                                                  "commission_threshold": "800000", "commission_percent_high": "6"},
                follow_redirects=False)
    db.expire_all()
    seller = db.get(type(seller), seller.id)
    assert (seller.commission_threshold, seller.commission_percent_high, seller.commission_percent) == (800000, 6, None)


# ---- Quincenas -----------------------------------------------------------------------------------------

@pytest.fixture
def periods(db):
    db.add_all([PayrollPeriod(start_date=date(2025, 12, 16), end_date=date(2025, 12, 31), status="final"),
                PayrollPeriod(start_date=date(2026, 10, 1), end_date=date(2026, 10, 15), status="final"),
                PayrollPeriod(start_date=date(2026, 10, 16), end_date=date(2026, 10, 31), status="draft")])
    db.commit()


def test_quincenas_filter_by_state_and_year(login_as, periods):
    client = login_as("admin")
    drafts = client.get("/payroll/?estado=borrador").text
    assert "Quincena 16–31 oct 2026" in drafts and "Quincena 1–15 oct 2026" not in drafts
    year = client.get("/payroll/?anio=2025").text
    assert "16–31 dic 2025" in year and "oct 2026" not in year.split("Quincenas</h2>")[1]
    assert client.get("/payroll/?anio=&estado=").status_code == 200
    assert "Ninguna quincena con esos filtros" in client.get("/payroll/?estado=borrador&anio=2025").text


# ---- Detail, Pagos and Liquidaciones --------------------------------------------------------------------

def test_detail_has_search_when_approved(db, login_as, periods):
    page = login_as("admin").get("/payroll/detail/2").text
    assert 'id="people-search"' in page and 'id="people-unpaid"' in page


def test_pagos_and_liquidaciones_search_and_show_inactive(db, login_as, users):
    make_user(db, "u_jose", "worker", full_name="José Rojas")
    make_user(db, "u_viejo", "worker", full_name="Pedro Liquidado", status="liquidated", is_active=False)
    client = login_as("admin")
    for path in ("/payments/", "/liquidation/"):
        default = client.get(path).text
        assert "José Rojas" in default and "Pedro Liquidado" not in default
        assert "Pedro Liquidado" in client.get(f"{path}?ver=todos").text
        found = client.get(f"{path}?q=jose").text  # without the accent
        assert "José Rojas" in found and users["worker"].full_name not in found


def test_own_single_percent_ignores_the_general_tiers(db, login_as, users, invoices):
    # A seller with their own 7 % from before the tiers keeps 7 % on every invoice.
    users["ventas"].commission_percent = 7
    db.commit()
    client = login_as("admin")
    for invoice in invoices:
        pay(client, invoice)
    db.expire_all()
    assert sorted(c.rate for c in db.query(Commission)) == [7, 7]
