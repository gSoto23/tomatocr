"""Posibles clientes: the sellers' prospecting list before the Filtro. Everyone who sells sees it
all; its seller and the admin work it; converting makes an account + opportunity in "Nueva"."""
from datetime import timedelta

import pytest

from app.db.models.crm import Account, Contact, CrmActivity, Opportunity
from app.db.models.prospect import Prospect, ProspectAttempt
from app.utils.crm import funnel, funnel_period
from app.utils.timecr import today_cr
from tests.conftest import make_user

TODAY = today_cr()
NEW = {"company": "Residencial Los Olivos", "contact_name": "Ana Rojas", "contact_role": "Administradora",
       "phone": "8888 1234", "email": "Admin@VistaReal.cr", "kind": "condominio", "motor": "mantenimiento",
       "province": "Heredia", "source": "directorio", "notes": "Tienen 40 casas", "next_contact_date": TODAY.isoformat()}


def add(client, **fields):
    return client.post("/clientes/posibles/nuevo", data={**NEW, **fields}, follow_redirects=False)


@pytest.mark.parametrize("role,allowed", [("admin", True), ("ventas", True), ("supervisor", False),
                                          ("worker", False), ("client", False)])
def test_who_uses_it(login_as, role, allowed):
    client = login_as(role)
    assert client.get("/clientes/posibles", follow_redirects=False).status_code == (200 if allowed else 403)


def test_add_and_list(db, login_as, users):
    client = login_as("ventas")
    assert add(client).status_code == 303
    p = db.query(Prospect).one()
    assert (p.owner_id, p.status, p.email, p.kind, p.motor) == (users["ventas"].id, "por_contactar", "admin@vistareal.cr",
                                                               "condominio", "mantenimiento")
    html = client.get("/clientes/posibles").text
    assert "Residencial Los Olivos" in html and "https://wa.me/50688881234" in html and "Convertir en oportunidad" in html
    assert 'href="/clientes/posibles"' in client.get("/clientes").text  # the tab
    assert "1 posible cliente para contactar hoy" in client.get("/dashboard/").text


def test_mistakes_and_repeats(db, login_as):
    client = login_as("ventas")
    response = add(client, phone="123")
    assert response.status_code == 400 and "Revisá el teléfono" in response.text and 'value="Residencial Los Olivos"' in response.text
    assert add(client, company=" ").status_code == 400
    add(client)
    again = add(client, company="Residencial Los Olivos S.A.", phone="", email="")
    assert again.status_code == 400 and "Puede que ya exista" in again.text and "Es otra empresa, guardarlo igual" in again.text
    assert add(client, company="Otra empresa", phone="+506 8888-1234", email="").status_code == 400  # same phone
    db.add(Account(name="Hotel Playa Azul"))
    db.commit()
    assert "Ya es una cuenta en Clientes" in add(client, company="Hotel Playa Azul", phone="", email="").text
    assert add(client, company="Hotel Playa Azul", phone="", email="", confirm="1").status_code == 303
    assert db.query(Prospect).count() == 2


def test_sellers_see_all_but_change_only_theirs(db, login_as, users):
    add(login_as("ventas"))
    p = db.query(Prospect).one()
    other = make_user(db, "otro_vendedor", "ventas")
    from tests.conftest import login, new_client
    client = new_client()
    login(client, "otro_vendedor")
    assert "Residencial Los Olivos" in client.get("/clientes/posibles?vendedor=todos").text
    assert "Residencial Los Olivos" not in client.get("/clientes/posibles").text  # opens on their own
    assert client.post(f"/clientes/posibles/{p.id}/intento", data={"channel": "llamada"}).status_code == 403
    assert client.post(f"/clientes/posibles/{p.id}/convertir").status_code == 403
    assert "Registrar intento" not in client.get(f"/clientes/posibles/{p.id}").text
    assert other.id != p.owner_id
    admin = login_as("admin")
    admin.post(f"/clientes/posibles/{p.id}/editar", data={**NEW, "owner_id": str(other.id)})
    db.refresh(p)
    assert p.owner_id == other.id  # the admin reassigns


def test_attempts_order_and_views(db, login_as, users):
    client = login_as("ventas")
    add(client, company="Llamar mañana", phone="", email="", next_contact_date=(TODAY + timedelta(days=1)).isoformat())
    add(client, company="Atrasado", phone="", email="", next_contact_date=(TODAY - timedelta(days=3)).isoformat())
    add(client, company="Sin fecha", phone="", email="", next_contact_date="")
    html = client.get("/clientes/posibles").text
    assert html.index("Atrasado") < html.index("Sin fecha") < html.index("Llamar mañana")
    late = db.query(Prospect).filter_by(company="Atrasado").one()
    client.post(f"/clientes/posibles/{late.id}/intento", data={"channel": "whatsapp", "notes": "Pidió precios",
                                                               "next_contact_date": (TODAY + timedelta(days=5)).isoformat()})
    db.refresh(late)
    assert late.status == "en_seguimiento" and late.attempts[0].notes == "Pidió precios" and late.last_contact_at
    hoy = client.get("/clientes/posibles?vista=hoy").text
    assert "Atrasado" not in hoy
    assert "1</strong> contactado" in client.get("/clientes/posibles").text


def test_convert_makes_account_and_opportunity_in_nueva(db, login_as, users):
    client = login_as("ventas")
    add(client)
    p = db.query(Prospect).one()
    client.post(f"/clientes/posibles/{p.id}/intento", data={"channel": "llamada", "notes": "Quiere visita"})
    response = client.post(f"/clientes/posibles/{p.id}/convertir", follow_redirects=False)
    db.expire_all()
    p = db.get(Prospect, p.id)
    opportunity = db.get(Opportunity, p.opportunity_id)
    assert response.headers["location"] == f"/clientes/oportunidades/{opportunity.id}"
    assert p.status == "convertido" and p.converted_at
    assert (opportunity.stage, opportunity.origin, opportunity.motor, opportunity.kind) == ("prospecto", "prospeccion",
                                                                                         "mantenimiento", "nuevo")
    assert opportunity.title == "Mantenimiento · Residencial Los Olivos" and opportunity.owner_id == users["ventas"].id
    account = db.get(Account, p.account_id)
    assert (account.name, account.kind, account.province, account.source) == ("Residencial Los Olivos", "condominio",
                                                                              "Heredia", "prospeccion")
    contact = db.query(Contact).filter_by(account_id=account.id).one()
    assert (contact.name, contact.email, contact.phone) == ("Ana Rojas", "admin@vistareal.cr", "8888 1234")
    notes = [a.notes for a in db.query(CrmActivity).filter_by(opportunity_id=opportunity.id)]
    assert any("Quiere visita" in n for n in notes) and any("Tienen 40 casas" in n for n in notes)
    assert funnel(db, owner_id=users["ventas"].id, period=funnel_period(db))  # counts like any opportunity
    assert client.post(f"/clientes/posibles/{p.id}/convertir", follow_redirects=False).headers["location"] == \
        f"/clientes/oportunidades/{opportunity.id}"  # twice: same one
    assert db.query(Opportunity).count() == 1
    assert client.post(f"/clientes/posibles/{p.id}/borrar").status_code in (200, 303)
    assert db.query(Prospect).count() == 1  # a converted one is not deleted


def test_convert_onto_an_existing_account(db, login_as, users):
    existing = Account(name="Residencial Los Olivos", owner_id=users["ventas"].id)
    db.add(existing)
    db.commit()
    client = login_as("ventas")
    add(client, confirm="1")
    p = db.query(Prospect).one()
    page = client.post(f"/clientes/posibles/{p.id}/convertir")
    assert "¿Ya es una de estas cuentas?" in page.text and db.query(Opportunity).count() == 0
    client.post(f"/clientes/posibles/{p.id}/convertir", data={"account_id": str(existing.id)})
    assert db.query(Account).count() == 1
    assert db.query(Opportunity).one().account_id == existing.id


def test_convert_as_new_account_when_it_is_another(db, login_as):
    db.add(Account(name="Residencial Los Olivos"))
    db.commit()
    client = login_as("ventas")
    add(client, confirm="1")
    p = db.query(Prospect).one()
    client.post(f"/clientes/posibles/{p.id}/convertir", data={"new_account": "1"})
    assert db.query(Account).count() == 2 and db.query(Opportunity).count() == 1


def test_not_interested_reactivate_and_delete(db, login_as):
    client = login_as("ventas")
    add(client)
    p = db.query(Prospect).one()
    assert client.post(f"/clientes/posibles/{p.id}/descartar", data={"reason": " "}, follow_redirects=False).status_code == 303
    db.refresh(p)
    assert p.status == "por_contactar"  # needs a reason
    client.post(f"/clientes/posibles/{p.id}/descartar", data={"reason": "Ya tienen jardinero"})
    db.refresh(p)
    assert p.status == "descartado" and p.next_contact_date is None
    assert "Residencial Los Olivos" not in client.get("/clientes/posibles").text
    assert "Ya tienen jardinero" in client.get("/clientes/posibles?vista=descartado").text
    client.post(f"/clientes/posibles/{p.id}/reactivar")
    db.refresh(p)
    assert p.status == "por_contactar" and p.discard_reason is None
    client.post(f"/clientes/posibles/{p.id}/borrar")
    assert db.query(Prospect).count() == 0 and db.query(ProspectAttempt).count() == 0


def test_search_filters_and_pages(db, login_as, users):
    db.add_all([Prospect(company=f"Empresa {i:02d}", owner_id=users["ventas"].id) for i in range(25)])
    db.add(Prospect(company="Hotel Montaña", contact_name="José Pérez", phone="7000-1234", province="Guanacaste",
                    motor="esg", owner_id=users["ventas"].id))
    db.commit()
    client = login_as("ventas")
    first = client.get("/clientes/posibles").text
    assert "Página 1 de 2" in first
    assert "Hotel Montaña" in client.get("/clientes/posibles?q=jose perez").text
    assert "Hotel Montaña" in client.get("/clientes/posibles?q=70001234").text
    only = client.get("/clientes/posibles?provincia=Guanacaste&motor=esg").text
    assert "Hotel Montaña" in only and "Empresa 00" not in only


def test_supervisor_who_sells_uses_it(db, login_as, users):
    users["supervisor"].also_sells = True
    db.commit()
    client = login_as("supervisor")
    assert add(client).status_code == 303
    assert db.query(Prospect).one().owner_id == users["supervisor"].id


def test_deleting_a_converted_account_takes_its_prospect(db, login_as):
    client = login_as("ventas")
    add(client)
    p = db.query(Prospect).one()
    client.post(f"/clientes/posibles/{p.id}/intento", data={"channel": "llamada", "notes": "Prueba"})
    client.post(f"/clientes/posibles/{p.id}/convertir")
    db.refresh(p)
    account_id = p.account_id
    admin = login_as("admin")
    admin.post(f"/clientes/cuentas/{account_id}/descartar", data={"reason": "Prueba"})
    response = admin.post(f"/clientes/cuentas/{account_id}/borrar", follow_redirects=False)
    assert response.status_code == 303
    db.expire_all()
    assert db.get(Account, account_id) is None and db.query(Opportunity).count() == 0
    assert db.query(Prospect).count() == 0 and db.query(ProspectAttempt).count() == 0


def test_deleting_an_account_keeps_other_prospects(db, login_as):
    client = login_as("ventas")
    add(client)
    add(client, company="Otra empresa distinta", phone="", email="", confirm="1")
    first = db.query(Prospect).filter_by(company="Residencial Los Olivos").one()
    client.post(f"/clientes/posibles/{first.id}/convertir")
    db.refresh(first)
    admin = login_as("admin")
    admin.post(f"/clientes/cuentas/{first.account_id}/descartar", data={"reason": "Prueba"})
    admin.post(f"/clientes/cuentas/{first.account_id}/borrar")
    assert [p.company for p in db.query(Prospect)] == ["Otra empresa distinta"]
