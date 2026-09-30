"""The quote tool's history: search, sent/not sent, issue dates and 10 per page."""
from datetime import date, datetime, timedelta

import pytest

from app.db.models.crm import Account
from app.db.models.quote import Quote, QuoteEmail


@pytest.fixture
def many(db):
    hotel = Account(name="Hotel Bosque")
    museo = Account(name="Museo de Arte")
    db.add_all([hotel, museo])
    db.flush()
    for n in range(1, 24):
        account = hotel if n % 2 else museo
        db.add(Quote(numero_cotizacion=f"TCR-2026-{n:04d}", fecha_emision=date(2026, 9, 1) + timedelta(days=n),
                     cliente_nombre=account.name, cliente_datos={"name": account.name}, moneda="CRC", total=n,
                     items=[], account_id=account.id))
    db.flush()
    db.add(QuoteEmail(quote_id=db.query(Quote).filter(Quote.numero_cotizacion == "TCR-2026-0005").one().id,
                      sent_at=datetime.utcnow(), recipients="a@b.cr", subject="x"))
    db.commit()


def history(client, **params):
    return client.get("/api/quotes/historial", params=params).json()


def test_ten_per_page_newest_first(login_as, many):
    client = login_as("ventas")
    first = history(client)
    assert (first["total"], first["pages"], len(first["items"])) == (23, 3, 10)
    assert first["items"][0]["numero_cotizacion"] == "TCR-2026-0023"
    last = history(client, page=3)
    assert len(last["items"]) == 3 and last["items"][-1]["numero_cotizacion"] == "TCR-2026-0001"
    assert history(client, page=99)["page"] == 3


def test_filters(login_as, many):
    client = login_as("admin")
    assert history(client, q="0017")["total"] == 1
    assert history(client, q="museo")["total"] == 11  # by client or account name
    sent = history(client, estado="enviadas")
    assert sent["total"] == 1 and sent["items"][0]["last_sent_at"]
    assert history(client, estado="sin_enviar")["total"] == 22
    assert history(client, desde="2026-09-20", hasta="2026-09-22")["total"] == 3
    assert login_as("admin").get("/api/quotes/historial", params={"desde": "ayer"}).status_code == 400


def test_client_sees_only_its_account(db, login_as, users, many):
    assert history(login_as("client"))["total"] == 0


def test_history_has_filters_and_pager(login_as):
    html = login_as("ventas").get("/cotizador").text
    assert 'id="recentFilters"' in html and 'id="recentPager"' in html and 'id="recentEstado"' in html
    assert 'id="recentEstado"' not in login_as("client").get("/cotizador").text
