"""A supervisor marked "También vende": Clientes and the Cotizador like ventas, without losing
anything of a supervisor."""
import pytest

from app.db.models.crm import Account, Opportunity
from app.db.models.user import User


@pytest.fixture
def seller_supervisor(db, users):
    users["supervisor"].also_sells = True
    db.commit()
    return users["supervisor"]


def test_a_plain_supervisor_does_not_sell(login_as, users):
    client = login_as("supervisor")
    assert client.get("/clientes", follow_redirects=False).status_code == 403
    assert client.get("/cotizador", follow_redirects=False).status_code == 403
    html = client.get("/dashboard/").text
    assert 'href="/clientes"' not in html and 'href="/cotizador"' not in html
    assert client.get("/manual/clientes").status_code == 404


def test_a_supervisor_who_sells_sees_clientes_and_the_quote_tool(login_as, seller_supervisor):
    client = login_as("supervisor")
    assert client.get("/clientes").status_code == 200 and client.get("/cotizador").status_code == 200
    assert "canSend: true" in client.get("/cotizador").text
    html = client.get("/dashboard/").text
    assert 'href="/clientes"' in html and 'href="/cotizador"' in html
    assert "Hoy en campo" in html and "Próximos pasos de hoy" in html and "Mis próximos pasos" in html
    assert "Mi filtro" in html
    assert client.get("/manual/clientes").status_code == 200
    # still a supervisor
    assert client.get("/payroll/approval").status_code == 200 and client.get("/calendar/").status_code == 200


def test_works_accounts_like_ventas(db, login_as, seller_supervisor):
    client = login_as("supervisor")
    client.post("/clientes/cuentas/nueva", data={"name": "Hotel Nuevo", "kind": "hotel", "contact_name": "Ana"},
                follow_redirects=False)
    account = db.query(Account).filter_by(name="Hotel Nuevo").one()
    assert account.owner_id == seller_supervisor.id
    client.post(f"/clientes/cuentas/{account.id}/oportunidades", data={"title": "Jardines"})
    assert db.query(Opportunity).filter_by(account_id=account.id).one().owner_id == seller_supervisor.id
    assert f'value="{seller_supervisor.id}"' in login_as("admin").get("/clientes/asignacion").text  # can be assigned leads


def test_the_box_is_only_for_supervisors(db, login_as):
    admin = login_as("admin")
    form = {"password": "clave-segura", "full_name": "X", "email": "x@example.com", "payment_method": "Efectivo",
            "is_active": "true", "also_sells": "true"}
    admin.post("/users/new", data={**form, "username": "sup2", "role": "supervisor"}, follow_redirects=False)
    admin.post("/users/new", data={**form, "username": "trab2", "role": "worker", "email": "y@example.com"},
               follow_redirects=False)
    assert db.query(User).filter_by(username="sup2").one().also_sells is True
    assert db.query(User).filter_by(username="trab2").one().also_sells is False
    assert "También vende" in admin.get("/users/new").text


def test_ventas_and_admin_unchanged(login_as, users):
    assert login_as("ventas").get("/clientes").status_code == 200
    assert login_as("worker").get("/clientes", follow_redirects=False).status_code == 403
    assert login_as("client").get("/cotizador").status_code == 200
    assert login_as("client").get("/clientes", follow_redirects=False).status_code == 403
