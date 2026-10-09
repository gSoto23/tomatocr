"""A quote saved in the Cotizador always has an opportunity, so it shows in Clientes; old quotes
without one get it from the account page. And the Dinero boxes of the Dashboard link right."""
from datetime import date

import pytest

from app.db.models.crm import Account, CrmActivity, Opportunity, stage_index
from app.db.models.quote import Quote
from tests.test_cotizador import YEAR, account, payload  # noqa: F401 (fixture)


def test_a_quote_without_opportunity_creates_one_in_propuesta(db, login_as, account, users):  # noqa: F811
    client = login_as("ventas")
    saved = client.post("/api/quotes/", json=payload(f"TCR-{YEAR}-0001", account.id, tipo_servicio="Mantenimiento")).json()
    assert saved["opportunity_created"] is True
    opportunity = db.get(Opportunity, saved["opportunity_id"])
    assert opportunity.account_id == account.id and opportunity.stage == "propuesta"
    assert opportunity.max_stage == stage_index("propuesta") and opportunity.kind == "nuevo"
    assert opportunity.title == f"Mantenimiento · TCR-{YEAR}-0001" and opportunity.owner_id == users["ventas"].id
    assert opportunity.amount_crc is None  # the amount comes from the quote
    assert opportunity.next_step == f"Dar seguimiento a la cotización TCR-{YEAR}-0001" and opportunity.next_step_date > date.today()
    assert db.query(CrmActivity).filter_by(opportunity_id=opportunity.id).count() == 1
    assert "Mantenimiento · TCR" in client.get("/clientes").text  # in the Filtro

    # Saving it again, with or without the opportunity in the request, does not make another.
    client.post("/api/quotes/", json=payload(f"TCR-{YEAR}-0001", account.id, id=saved["id"],
                                             opportunity_id=saved["opportunity_id"]))
    again = client.post("/api/quotes/", json=payload(f"TCR-{YEAR}-0001", account.id, id=saved["id"])).json()
    assert again["opportunity_created"] is False and again["opportunity_id"] == saved["opportunity_id"]
    assert db.query(Opportunity).count() == 1


def test_a_quote_from_an_opportunity_uses_it(db, login_as, account):  # noqa: F811
    opportunity = Opportunity(account_id=account.id, title="Jardines", stage="reunion", max_stage=stage_index("reunion"))
    db.add(opportunity)
    db.commit()
    saved = login_as("ventas").post("/api/quotes/", json=payload(f"TCR-{YEAR}-0002", account.id,
                                                                 opportunity_id=opportunity.id)).json()
    assert saved["opportunity_id"] == opportunity.id and saved["opportunity_created"] is False
    assert db.query(Opportunity).count() == 1


def test_a_client_account_gets_an_extension(db, login_as, account, monkeypatch):  # noqa: F811
    monkeypatch.setattr("app.utils.crm.account_status", lambda db, account: "cliente")
    saved = login_as("ventas").post("/api/quotes/", json=payload(f"TCR-{YEAR}-0003", account.id)).json()
    opportunity = db.get(Opportunity, saved["opportunity_id"])
    assert opportunity.kind == "ampliacion" and opportunity.origin == "cliente_actual"
    assert opportunity.title == f"Cotización · TCR-{YEAR}-0003"


def test_a_client_user_does_not_create_opportunities(db, login_as, users):
    from app.db.models.crm import Contact
    own = Account(name="Empresa Cliente")
    db.add(own)
    db.flush()
    db.add(Contact(account_id=own.id, name="C", email=users["client"].email, user_id=users["client"].id))
    db.commit()
    response = login_as("client").post("/api/quotes/", json=payload(f"TCR-{YEAR}-0004", None))
    if response.status_code == 200:
        assert response.json()["opportunity_id"] is None
    assert db.query(Opportunity).count() == 0


def test_old_quote_gets_its_opportunity_from_the_account(db, login_as, account):  # noqa: F811
    quote = Quote(numero_cotizacion=f"TCR-{YEAR}-0011", fecha_emision=date.today(), cliente_nombre="OIJ",
                  tipo_servicio="Poda", account_id=account.id)
    db.add(quote)
    db.commit()
    client = login_as("ventas")
    page = client.get(f"/clientes/cuentas/{account.id}").text
    action = f"/clientes/cuentas/{account.id}/cotizaciones/{quote.id}/oportunidad"
    assert action in page
    response = client.post(action, follow_redirects=False)
    db.expire_all()
    quote = db.get(Quote, quote.id)
    assert quote.opportunity_id and response.headers["location"].startswith(f"/clientes/oportunidades/{quote.opportunity_id}")
    assert db.get(Opportunity, quote.opportunity_id).stage == "propuesta"
    page = client.get(f"/clientes/cuentas/{account.id}").text
    assert action not in page and f"/clientes/oportunidades/{quote.opportunity_id}" in page
    client.post(action)  # twice: still one
    assert db.query(Opportunity).count() == 1


def test_only_who_can_edit_the_account(db, login_as, account, users):  # noqa: F811
    quote = Quote(numero_cotizacion=f"TCR-{YEAR}-0012", fecha_emision=date.today(), cliente_nombre="X", account_id=account.id)
    db.add(quote)
    db.commit()
    action = f"/clientes/cuentas/{account.id}/cotizaciones/{quote.id}/oportunidad"
    assert login_as("worker").post(action, follow_redirects=False).status_code in (303, 403)
    assert db.query(Opportunity).count() == 0


@pytest.mark.parametrize("href", ['href="#facturas"', 'href="/dashboard?invoice_status=vencida#facturas"', 'href="/finance"'])
def test_dinero_boxes_link_right(login_as, href):
    html = login_as("admin").get("/dashboard/").text
    assert href in html and "&#34;" not in html.split("Por cobrar")[0][-400:]
