"""Descartados: discard a client from the account or the opportunity, the separate list,
reactivating, deleting junk for good, newest-first tables and the renamed texts."""
from datetime import date

import pytest

from app.db.models.activity import ActivityLog
from app.db.models.crm import Account, Contact, CrmActivity, Opportunity, stage_index
from app.db.models.project import Project
from app.db.models.quote import Quote
from tests.conftest import login, make_user, new_client
from tests.test_crm_entradas import FORM, mails, post_form, sellers  # noqa: F401 (fixtures)


@pytest.fixture
def junk(db, users):
    """A spam account from the form, owned by u_ventas, with a contact, an open opportunity and a note."""
    account = Account(name="Spam SA", owner_id=users["ventas"].id, source="web")
    db.add(account)
    db.flush()
    contact = Contact(account_id=account.id, name="Bot", email="bot@spam.test")
    opportunity = Opportunity(account_id=account.id, title="Mantenimiento · Formulario", motor="mantenimiento",
                              stage="prospecto", owner_id=users["ventas"].id)
    db.add_all([contact, opportunity])
    db.flush()
    db.add(CrmActivity(account_id=account.id, opportunity_id=opportunity.id, contact_id=contact.id, type="nota",
                       notes="Solicitud"))
    db.commit()
    return {"account": account, "opportunity": opportunity}


def discard(client, junk, reason="Spam"):
    return client.post(f"/clientes/oportunidades/{junk['opportunity'].id}/descartar", data={"reason": reason},
                       follow_redirects=False)


def test_discard_from_the_opportunity_moves_the_client_to_descartados(db, login_as, junk):
    client = login_as("ventas")
    assert "Descartar cliente" in client.get(f"/clientes/oportunidades/{junk['opportunity'].id}").text
    assert "Spam SA" in client.get("/clientes").text and "Spam SA" in client.get("/clientes/cuentas").text
    response = discard(client, junk, "Es spam")
    assert response.status_code == 303 and response.headers["location"] == "/clientes"
    db.expire_all()
    account = db.get(Account, junk["account"].id)
    assert account.discarded_at and account.discard_reason == "Es spam"
    opportunity = db.get(Opportunity, junk["opportunity"].id)
    assert opportunity.stage == "perdido" and "Es spam" in opportunity.lost_reason
    assert "Spam SA" not in client.get("/clientes").text
    assert "Spam SA" not in client.get("/clientes/cuentas").text
    page = client.get("/clientes/descartados").text
    assert "Spam SA" in page and "Es spam" in page and "Reactivar" in page


def test_discarding_needs_a_reason_and_the_owner(db, login_as, junk, users):
    assert discard(login_as("ventas"), junk, "  ").status_code == 303
    db.expire_all()
    assert db.get(Account, junk["account"].id).discarded_at is None
    admin = login_as("admin")
    assert admin.post(f"/clientes/cuentas/{junk['account'].id}/descartar", follow_redirects=False).status_code == 303
    db.expire_all()
    assert db.get(Account, junk["account"].id).discarded_at is None  # no reason, nothing changes
    make_user(db, "otra_ventas", "ventas")
    other = new_client()
    login(other, "otra_ventas")
    assert discard(other, junk).status_code == 403


def test_old_estado_filter_goes_to_descartados(login_as):
    response = login_as("admin").get("/clientes/cuentas?estado=descartada", follow_redirects=False)
    assert response.headers["location"] == "/clientes/descartados"


def test_reactivate_brings_it_back(db, login_as, junk):
    client = login_as("ventas")
    discard(client, junk)
    response = client.post(f"/clientes/cuentas/{junk['account'].id}/descartar", data={"back": "descartados"},
                           follow_redirects=False)
    assert response.headers["location"] == "/clientes/descartados"
    db.expire_all()
    account = db.get(Account, junk["account"].id)
    assert account.discarded_at is None and account.discard_reason is None
    assert "Spam SA" in client.get("/clientes/cuentas").text


def test_admin_deletes_junk_for_good(db, login_as, junk):
    discard(login_as("ventas"), junk)
    assert login_as("ventas").post(f"/clientes/cuentas/{junk['account'].id}/borrar").status_code == 403
    admin = login_as("admin")
    assert "Borrar" in admin.get("/clientes/descartados").text
    response = admin.post(f"/clientes/cuentas/{junk['account'].id}/borrar", follow_redirects=False)
    assert response.status_code == 303
    db.expire_all()
    assert db.query(Account).count() == 0 and db.query(Contact).count() == 0
    assert db.query(Opportunity).count() == 0 and db.query(CrmActivity).count() == 0
    assert db.query(ActivityLog).filter(ActivityLog.action == "DELETE", ActivityLog.entity_type == "ACCOUNT").count() == 1


def test_only_discarded_accounts_without_history_can_be_deleted(db, login_as, junk, users):
    admin = login_as("admin")
    admin.post(f"/clientes/cuentas/{junk['account'].id}/borrar")  # not discarded yet
    db.expire_all()
    assert db.get(Account, junk["account"].id) is not None
    discard(admin, junk)
    db.add(Quote(numero_cotizacion="TCR-2026-0200", fecha_emision=date.today(), cliente_nombre="Spam SA",
                 cliente_datos={}, moneda="CRC", total=10, items=[], account_id=junk["account"].id))
    project = db.get(Project, users["project_id"])
    project.account_id = junk["account"].id
    db.commit()
    assert "tiene proyectos, tiene cotizaciones" in admin.get("/clientes/descartados").text
    admin.post(f"/clientes/cuentas/{junk['account'].id}/borrar")
    db.expire_all()
    assert db.get(Account, junk["account"].id) is not None


def test_a_new_request_reactivates_a_discarded_account(db, sellers, mails, login_as):  # noqa: F811
    post_form(FORM)
    account = db.query(Account).one()
    discard(login_as("admin"), {"opportunity": db.query(Opportunity).one()}, "No contestó")
    post_form(FORM, ip="200.1.113.11")
    db.expire_all()
    assert db.get(Account, account.id).discarded_at is None
    assert db.query(Opportunity).filter(Opportunity.stage == "prospecto").count() == 1


def test_tables_show_the_newest_first(db, login_as, users):
    for name in ("Primera SA", "Segunda SA", "Tercera SA"):
        account = Account(name=name)
        db.add(account)
        db.flush()
        db.add(Opportunity(account_id=account.id, title=f"Oportunidad {name}", stage="respuesta",
                           max_stage=stage_index("respuesta")))
    db.commit()
    client = login_as("admin")
    for url in ("/clientes", "/clientes/cuentas"):
        html = client.get(url).text
        assert html.index("Tercera SA") < html.index("Segunda SA") < html.index("Primera SA")


def test_new_names_on_screen(login_as, junk):
    client = login_as("admin")
    html = client.get("/clientes").text
    nav = html.split("<nav", 2)[-1].split("</nav>", 1)[0]
    assert "Filtro" in nav and "Embudo" not in nav and "Descartados" in nav
    assert "Filtro ·" in html and ">Buscar</button>" in html and ">Filtrar</button>" not in html
    assert "Nueva" in html  # first stage
    assert "Asignación de oportunidades" in html
    assert "Oportunidad" in client.get(f"/clientes/cuentas/{junk['account'].id}").text
