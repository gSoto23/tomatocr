"""Sending a quote by e-mail from the quote tool: the PDF made by the server, from the
notifications account with replies to the seller, and what it records in Clientes."""
from datetime import date

import pytest

from app.db.models.crm import Account, Contact, CrmActivity, Opportunity, stage_index
from app.db.models.quote import Quote, QuoteEmail
from app.routers import quotes as quotes_router
from app.utils import quote_pdf as quote_pdf_module
from app.utils.quote_pdf import business_days_after, default_email, money, totals


@pytest.fixture
def sent(monkeypatch):
    """No real e-mail and no WeasyPrint needed: records what would be sent."""
    calls = []

    async def fake_send(recipients, subject, message, pdf, filename, reply_to):
        calls.append({"to": recipients, "subject": subject, "message": message, "pdf": pdf, "filename": filename,
                      "reply_to": reply_to})
        return True
    monkeypatch.setattr(quotes_router, "send_quote_email", fake_send)
    monkeypatch.setattr(quotes_router, "quote_pdf", lambda q: b"%PDF-1.7 prueba")
    return calls


@pytest.fixture
def quote(db, users):
    account = Account(name="Hotel Bosque", owner_id=users["ventas"].id)
    db.add(account)
    db.flush()
    db.add(Contact(account_id=account.id, name="Laura Mora", email="laura@hotelbosque.cr", is_primary=True))
    opportunity = Opportunity(account_id=account.id, title="Jardines", motor="mantenimiento", stage="reunion",
                              max_stage=stage_index("reunion"), owner_id=users["ventas"].id)
    db.add(opportunity)
    db.flush()
    q = Quote(numero_cotizacion="TCR-2026-0300", fecha_emision=date(2026, 9, 29), cliente_nombre="Hotel Bosque",
              cliente_datos={"name": "Hotel Bosque", "id": "Laura Mora", "email": ""}, moneda="CRC",
              tipo_servicio="Jardinería", validez_dias=15, subtotal=900000, iva=117000, total=1017000,
              tax_rate=13, items=[{"type": "Servicio", "description": "Mantenimiento", "unit": "Mes", "qty": 1,
                                   "unitPrice": 900000}], account_id=account.id, opportunity_id=opportunity.id)
    db.add(q)
    db.commit()
    return q


def post(client, q, **data):
    body = {"to": "laura@hotelbosque.cr", "subject": "Cotización", "message": "Hola Laura", "next_step_date": "2026-10-02"}
    body.update(data)
    return client.post(f"/api/quotes/{q.id}/email", json=body)


def test_the_window_starts_filled_in(login_as, quote):
    data = login_as("ventas").get(f"/api/quotes/{quote.id}/email").json()
    assert data["to"] == ["laura@hotelbosque.cr"]  # the account's main contact: the quote had no e-mail
    assert data["subject"] == "Cotización TCR-2026-0300 · TOMATO" and data["filename"] == "TCR-2026-0300.pdf"
    assert data["message"].startswith("Hola Laura:") and "₡1 017 000,00" in data["message"]
    assert "válida hasta el 14/10/2026" in data["message"]
    assert data["opportunity"]["open"] and data["history"] == []


def test_send_records_everything(db, login_as, users, quote, sent):
    response = post(login_as("ventas"), quote)
    assert response.status_code == 200, response.text
    assert sent[0]["to"] == ["laura@hotelbosque.cr"] and sent[0]["filename"] == "TCR-2026-0300.pdf"
    assert sent[0]["pdf"].startswith(b"%PDF") and sent[0]["reply_to"] == [users["ventas"].email]
    row = db.query(QuoteEmail).one()
    assert row.recipients == "laura@hotelbosque.cr" and row.sent_by_id == users["ventas"].id
    note = db.query(CrmActivity).filter(CrmActivity.type == "correo").one()
    assert "TCR-2026-0300" in note.notes
    db.refresh(quote)
    opportunity = db.get(Opportunity, quote.opportunity_id)
    assert opportunity.stage == "propuesta"
    assert opportunity.next_step == "Dar seguimiento a la cotización TCR-2026-0300"
    assert opportunity.next_step_date == date(2026, 10, 2)
    assert response.json()["history"][0]["to"] == "laura@hotelbosque.cr"
    listed = login_as("ventas").get("/api/quotes/").json()
    assert listed[0]["last_sent_at"]


def test_bad_recipients_are_refused(db, login_as, quote, sent):
    client = login_as("ventas")
    assert post(client, quote, to="").status_code == 400
    assert "Revisá este correo" in post(client, quote, to="laura@, otro@x.cr").json()["detail"]
    assert post(client, quote, to=",".join(f"p{i}@x.cr" for i in range(6))).status_code == 400
    assert post(client, quote, message=" ").status_code == 400
    assert sent == [] and db.query(QuoteEmail).count() == 0


def test_a_failed_send_records_nothing(db, login_as, quote, sent, monkeypatch):
    async def fail(*args):
        return False
    monkeypatch.setattr(quotes_router, "send_quote_email", fail)
    response = post(login_as("ventas"), quote)
    assert response.status_code == 502 and "No se pudo enviar" in response.json()["detail"]
    assert db.query(QuoteEmail).count() == 0 and db.query(CrmActivity).count() == 0


def test_only_admin_and_sales_send(login_as, quote, sent):
    assert login_as("client").post(f"/api/quotes/{quote.id}/email", json={}).status_code in (403, 404)
    assert login_as("worker").get(f"/api/quotes/{quote.id}/email").status_code == 403
    assert "canSend: true" in login_as("ventas").get("/cotizador").text
    assert "canSend: false" in login_as("client").get("/cotizador").text


def test_pdf_preview_and_a_missing_pdf_engine(login_as, quote, monkeypatch):
    monkeypatch.setattr(quotes_router, "quote_pdf", lambda q: b"%PDF-1.7 prueba")
    response = login_as("ventas").get(f"/api/quotes/{quote.id}/pdf")
    assert response.headers["content-type"] == "application/pdf" and "TCR-2026-0300.pdf" in response.headers["content-disposition"]

    def broken(q):
        raise OSError("no pango")
    monkeypatch.setattr(quotes_router, "quote_pdf", broken)
    response = login_as("ventas").get(f"/api/quotes/{quote.id}/pdf")
    assert response.status_code == 503 and "PDF" in response.json()["detail"]


def test_pdf_content_matches_the_quote_tool(quote):
    html = quote_pdf_module.quote_html(quote)
    assert "TCR-2026-0300" in html and "Hotel Bosque" in html and "Laura Mora" in html
    assert "₡1 017 000,00" in html and "IVA (13 %)" in html and "Aceptación del cliente" in html
    assert money(1234.5, "USD") == "$1,234.50"
    assert totals(quote)["total"] == pytest.approx(1017000)


def test_pdf_is_a_real_pdf(quote):
    pytest.importorskip("weasyprint", exc_type=Exception)  # needs Pango on the machine
    assert quote_pdf_module.quote_pdf(quote).startswith(b"%PDF")


def test_follow_up_skips_the_weekend():
    assert business_days_after(date(2026, 10, 2), 3) == date(2026, 10, 7)  # Friday + 3 business days
