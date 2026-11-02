"""Planilla, phase 5: sellers' commissions when an invoice becomes PAGADA (a % without IVA)
and once per new client, paid through the payroll and cancellable with a trace."""
from datetime import date

import pytest

from app.db.models.commission import Commission
from app.db.models.crm import Account, Opportunity
from app.db.models.finance import BudgetLine, Invoice, ProjectBudget
from app.db.models.payroll import PayrollAdjustment, PayrollEntry
from app.db.models.project import Project
from app.db.models.user import User
from app.utils.comisiones import set_general_rules
from tests.conftest import PASSWORD

TODAY = date(2026, 11, 2)


@pytest.fixture
def sale(db, users):
    """A won "Nuevo" opportunity of the asesor, its project and a ₡113 000 invoice (₡100 000 + 13% IVA)."""
    seller = users["ventas"]
    account = Account(name="Hotel Arenal", owner_id=users["admin"].id)
    db.add(account)
    db.flush()
    opportunity = Opportunity(account_id=account.id, title="Jardines del hotel", kind="nuevo", stage="ganado",
                              owner_id=seller.id)
    db.add(opportunity)
    db.flush()
    project = db.get(Project, users["project_id"])
    project.account_id, project.opportunity_id = account.id, opportunity.id
    budget = ProjectBudget(project_id=project.id)
    db.add(budget)
    db.flush()
    line = BudgetLine(budget_id=budget.id, name="Mantenimiento", subtotal=1000000, tax_percentage=13)
    db.add(line)
    db.flush()
    invoices = [Invoice(budget_id=budget.id, budget_line_id=line.id, invoice_number=f"FE-{n}", issue_date=TODAY,
                        due_date=TODAY, amount=113000) for n in (1, 2)]
    db.add_all(invoices)
    set_general_rules(db, 5, 50000)
    db.commit()
    return {"seller": seller, "account": account, "opportunity": opportunity, "invoices": invoices}


def pay(client, invoice, amount=113000, kind="full"):
    return client.post(f"/finance/invoice/{invoice.id}/pay", data={
        "payment_date": "2026-11-02", "deposit_number": f"D-{invoice.id}-{amount}", "amount": amount,
        "retention_amount": 0, "payment_type": kind, "note": ""}, follow_redirects=False)


def commissions(db):
    db.expire_all()
    return {c.kind: c for c in db.query(Commission).order_by(Commission.id)}


# ---- When they are born ---------------------------------------------------------------------------

def test_paid_invoice_gives_percent_without_iva_and_new_client(db, login_as, sale):
    assert pay(login_as("admin"), sale["invoices"][0]).status_code == 303
    found = commissions(db)
    assert found["factura"].base_amount == 100000 and found["factura"].amount == 5000
    assert found["factura"].user_id == sale["seller"].id and found["factura"].client_name == "Hotel Arenal"
    assert found["factura"].payment_date == date(2026, 11, 2) and found["factura"].invoice_number == "FE-1"
    assert found["cliente_nuevo"].amount == 50000
    # Both wait for the next payroll as adjustments.
    assert sorted(a.amount for a in db.query(PayrollAdjustment)) == [5000, 50000]


def test_partial_payment_waits_until_paid(db, login_as, sale):
    client = login_as("admin")
    pay(client, sale["invoices"][0], 50000, kind="partial")
    assert commissions(db) == {}
    pay(client, sale["invoices"][0], 63000, kind="full")
    assert set(commissions(db)) == {"factura", "cliente_nuevo"}


def test_new_client_is_paid_once(db, login_as, sale):
    client = login_as("admin")
    pay(client, sale["invoices"][0])
    pay(client, sale["invoices"][1])
    kinds = [c.kind for c in db.query(Commission)]
    assert kinds.count("cliente_nuevo") == 1 and kinds.count("factura") == 2


def test_paying_again_does_not_duplicate(db, login_as, sale):
    client = login_as("admin")
    pay(client, sale["invoices"][0])
    pay(client, sale["invoices"][0], 1000)
    assert db.query(Commission).count() == 2


def test_renewal_has_no_new_client_commission(db, login_as, sale):
    sale["opportunity"].kind = "renovacion"
    db.commit()
    pay(login_as("admin"), sale["invoices"][0])
    assert set(commissions(db)) == {"factura"}


def test_own_rules_win_and_zero_means_none(db, login_as, sale):
    seller = sale["seller"]
    seller.commission_percent, seller.commission_new_client = 10, 0
    db.commit()
    pay(login_as("admin"), sale["invoices"][0])
    found = commissions(db)
    assert found["factura"].amount == 10000 and "cliente_nuevo" not in found


def test_admin_seller_earns_only_with_own_rules(db, login_as, users, sale):
    sale["opportunity"].owner_id = users["admin"].id
    db.commit()
    pay(login_as("admin"), sale["invoices"][0])
    assert commissions(db) == {}


def test_without_opportunity_the_account_owner_earns(db, login_as, users, sale):
    project = db.get(Project, users["project_id"])
    project.opportunity_id = None
    sale["account"].owner_id = sale["seller"].id
    db.commit()
    pay(login_as("admin"), sale["invoices"][0])
    # No opportunity: only the invoice commission (new client needs a "Nuevo" opportunity).
    assert set(commissions(db)) == {"factura"}


# ---- Paid through the payroll ------------------------------------------------------------------------

def generate(client, start="2026-11-01", end="2026-11-15"):
    response = client.post("/payroll/generate", json={"start_date": start, "end_date": end})
    assert response.status_code == 200, response.text
    return response.json()["period_id"]


def test_commission_joins_the_next_payroll_and_shows_where(db, login_as, sale):
    client = login_as("admin")
    pay(client, sale["invoices"][0])
    period_id = generate(client)
    entry = db.query(PayrollEntry).filter(PayrollEntry.user_id == sale["seller"].id).one()
    assert sorted(l.amount for l in entry.lines) == [5000, 50000] and entry.gross_salary == 55000
    page = client.get("/payroll/commissions").text
    assert "En planilla (borrador)" in page and f"planilla #{period_id}" in page
    client.post("/payroll/confirm", json={"period_id": period_id})
    assert "Pagada" in client.get("/payroll/commissions").text


# ---- Cancelling ---------------------------------------------------------------------------------------------

def cancel(client, commission, reason="La factura se anuló"):
    return client.post(f"/payroll/commissions/{commission.id}/cancel", json={"reason": reason})


def test_cancel_before_payroll_removes_it(db, login_as, sale):
    client = login_as("admin")
    pay(client, sale["invoices"][0])
    commission = commissions(db)["factura"]
    response = cancel(client, commission)
    assert response.status_code == 200 and response.json()["message"] == "Comisión anulada"
    assert [a.amount for a in db.query(PayrollAdjustment)] == [50000]
    assert commissions(db)["factura"].cancel_reason == "La factura se anuló"


def test_cancel_in_a_draft_takes_it_out(db, login_as, sale):
    client = login_as("admin")
    pay(client, sale["invoices"][0])
    generate(client)
    response = cancel(client, commissions(db)["factura"])
    assert "borrador" in response.json()["message"]
    entry = db.query(PayrollEntry).filter(PayrollEntry.user_id == sale["seller"].id).one()
    db.refresh(entry)
    assert [l.amount for l in entry.lines] == [50000] and entry.gross_salary == 50000


def test_cancel_after_paid_takes_it_back_next_time(db, login_as, sale):
    client = login_as("admin")
    pay(client, sale["invoices"][0])
    first = generate(client)
    client.post("/payroll/confirm", json={"period_id": first})
    response = cancel(client, commissions(db)["factura"])
    assert "próxima planilla" in response.json()["message"]
    reversal = db.query(PayrollAdjustment).filter(PayrollAdjustment.amount == -5000).one()
    assert reversal.source_period_id == first
    assert "Revertida" in client.get("/payroll/commissions").text


def test_cancel_needs_a_reason_and_only_once(db, login_as, sale):
    client = login_as("admin")
    pay(client, sale["invoices"][0])
    commission = commissions(db)["factura"]
    assert cancel(client, commission, " ").status_code == 400
    assert cancel(client, commission).status_code == 200
    assert cancel(client, commission).status_code == 400


def test_a_commission_adjustment_is_cancelled_only_from_commissions(db, login_as, sale):
    client = login_as("admin")
    pay(client, sale["invoices"][0])
    adjustment = db.query(PayrollAdjustment).first()
    response = client.post(f"/payroll/adjustments/{adjustment.id}/delete")
    assert response.status_code == 400 and "Comisiones" in response.json()["detail"]


# ---- Who sees what ----------------------------------------------------------------------------------------

def test_seller_sees_only_own_commissions(db, login_as, users, sale):
    pay(login_as("admin"), sale["invoices"][0])
    page = login_as("ventas").get("/payroll/commissions")
    assert page.status_code == 200 and "Mis comisiones" in page.text and "Reglas generales" not in page.text
    other = User(username="otro_ventas", hashed_password=users["ventas"].hashed_password, full_name="Otra",
                 role="ventas", is_active=True, status="active")
    db.add(other)
    db.commit()
    db.add(Commission(user_id=other.id, kind="factura", amount=1, client_name="Ajeno"))
    db.commit()
    assert "Ajeno" not in login_as("ventas").get("/payroll/commissions").text


@pytest.mark.parametrize("role", ["worker", "supervisor"])
def test_people_who_do_not_sell_have_no_commissions_page(login_as, role):
    assert login_as(role).get("/payroll/commissions").status_code == 403


@pytest.mark.parametrize("role", ["supervisor", "ventas"])
def test_only_admin_sets_rules_and_cancels(login_as, role):
    client = login_as(role)
    assert client.post("/payroll/commissions/settings", data={"percent": 50}).status_code == 403
    assert client.post("/payroll/commissions/1/cancel", json={"reason": "x"}).status_code == 403


def test_admin_saves_general_rules(db, login_as):
    client = login_as("admin")
    client.post("/payroll/commissions/settings", data={"percent": "3.5", "new_client": "25000"})
    page = client.get("/payroll/commissions").text
    assert 'value="3.5"' in page and 'value="25000.0"' in page
    assert client.post("/payroll/commissions/settings", data={"percent": "150"},
                       follow_redirects=False).headers["location"].endswith("error=valores")


def test_employee_form_keeps_own_rules_or_empty(db, login_as):
    client = login_as("admin")
    base = {"username": "nuevo", "password": PASSWORD, "full_name": "Nuevo", "role": "ventas", "is_active": "true",
            "email": "n@example.com"}
    client.post("/users/new", data={**base, "commission_percent": "7", "commission_new_client": ""},
                follow_redirects=False)
    person = db.query(User).filter(User.username == "nuevo").one()
    assert person.commission_percent == 7 and person.commission_new_client is None


def test_commissions_page_lists_sellers_and_a_working_cancel_button(db, login_as, users, sale):
    pay(login_as("admin"), sale["invoices"][0])
    page = login_as("admin").get("/payroll/commissions").text
    # An admin without own rules earns nothing, so isn't listed among those who earn.
    assert f'href="/users/{users["admin"].id}/edit"' not in page
    # The state goes inside a single-quoted attribute: its double quotes must not cut it.
    assert "onclick='cancelCommission(" in page


def test_commission_adjustments_point_to_commissions(db, login_as, sale):
    client = login_as("admin")
    pay(client, sale["invoices"][0])
    page = client.get("/payroll/").text
    assert "Ver en Comisiones" in page and "deleteAdjustment(" not in page.split("Periodos de Planilla")[0]
