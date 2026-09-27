"""Quote tool: saved discount and VAT rate, safe numbering, printable page."""
from datetime import date

import pytest

from app.db.models.crm import Account
from app.db.models.quote import Quote

YEAR = date.today().year


@pytest.fixture
def account(db, users):
    account = Account(name="Hotel Playa Azul", owner_id=users["ventas"].id)
    db.add(account)
    db.commit()
    return account


def payload(number, account_id, **extra):
    data = {"numero_cotizacion": number, "fecha_emision": date.today().isoformat(), "cliente_nombre": "Hotel",
            "cliente_datos": {"name": "Hotel"}, "moneda": "CRC", "subtotal": 100000, "iva": 12350, "total": 107350,
            "items": [], "account_id": account_id}
    data.update(extra)
    return data


def test_discount_and_tax_rate_are_saved_and_returned(db, login_as, account):
    client = login_as("ventas")
    response = client.post("/api/quotes/", json=payload(f"TCR-{YEAR}-0001", account.id, discount=5000, tax_rate=13))
    assert response.status_code == 200
    saved = client.get(f"/api/quotes/{response.json()['id']}").json()
    assert saved["discount"] == 5000 and saved["tax_rate"] == 13

    client.post("/api/quotes/", json=payload(f"TCR-{YEAR}-0001", account.id, discount=0, tax_rate=0))
    db.expire_all()
    quote = db.query(Quote).filter_by(numero_cotizacion=f"TCR-{YEAR}-0001").one()
    assert (quote.discount, quote.tax_rate) == (0, 0)


def test_bad_or_negative_numbers_fall_back(db, login_as, account):
    login_as("ventas").post("/api/quotes/", json=payload(f"TCR-{YEAR}-0002", account.id, discount=-10, tax_rate="x"))
    quote = db.query(Quote).filter_by(numero_cotizacion=f"TCR-{YEAR}-0002").one()
    assert (quote.discount, quote.tax_rate) == (0, 13)


def test_next_number_follows_the_highest_of_the_year(db, login_as, account):
    client = login_as("ventas")
    assert client.get("/api/quotes/next-number").json() == {"next_number": 1}
    db.add_all([
        Quote(numero_cotizacion=f"TCR-{YEAR}-0003", fecha_emision=date.today(), cliente_nombre="A", account_id=account.id),
        Quote(numero_cotizacion=f"TCR-{YEAR}-0010", fecha_emision=date.today(), cliente_nombre="B", account_id=account.id),
        Quote(numero_cotizacion=f"TCR-{YEAR - 1}-0099", fecha_emision=date.today(), cliente_nombre="C", account_id=account.id),
        Quote(numero_cotizacion="OTRO-FORMATO", fecha_emision=date.today(), cliente_nombre="D", account_id=account.id),
    ])
    db.commit()
    # Only 4 quotes exist, but the next number must be 11, not 5: a gap never reuses a number.
    assert client.get("/api/quotes/next-number").json() == {"next_number": 11}


def test_the_page_has_the_review_panel_and_numbered_sections(login_as, account):
    html = login_as("ventas").get("/cotizador").text
    assert 'id="qualityPanel"' in html
    for heading in ["1. Cliente y servicio", "2. Ítems", "3. Condiciones"]:
        assert heading in html
    assert "Supabase" not in html
