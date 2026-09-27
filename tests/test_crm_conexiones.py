"""Fase 2C: quote tool, projects and daily-log email connected to Clientes; win and renew."""
from datetime import date, timedelta

import pytest

from app.db.models.crm import Account, Contact, CrmActivity, Opportunity, ProjectContactRole, stage_index
from app.db.models.finance import ProjectBudget
from app.db.models.log import DailyLog
from app.db.models.project import Project
from app.db.models.project_details import ProjectContact
from app.db.models.quote import Quote
from app.utils.crm import expiring_contracts
from tests.conftest import make_user

TODAY = date.today()


@pytest.fixture
def world(db, users):
    """Client user u_client belongs to Museo; Tical is another account owned by u_ventas."""
    museo = Account(name="Museo de Arte")
    tical = Account(name="Tical", owner_id=users["ventas"].id)
    other_seller = make_user(db, "otra_ventas", "ventas")
    ajena = Account(name="Cuenta Ajena", owner_id=other_seller.id)
    db.add_all([museo, tical, ajena])
    db.flush()
    db.add(Contact(account_id=museo.id, name="Portal Museo", user_id=users["client"].id))
    ana = Contact(account_id=tical.id, name="Ana", email="ana@tical.cr", is_primary=True)
    pedro = Contact(account_id=tical.id, name="Pedro", phone="8000-0000")
    intrusa = Contact(account_id=ajena.id, name="Intrusa", email="x@ajena.cr")
    db.add_all([ana, pedro, intrusa])
    db.add_all([
        Quote(numero_cotizacion="Q-MUSEO", fecha_emision=TODAY, cliente_nombre="Museo", account_id=museo.id, total=10),
        Quote(numero_cotizacion="Q-TICAL", fecha_emision=TODAY, cliente_nombre="Tical", account_id=tical.id, total=20),
    ])
    opp = Opportunity(account_id=tical.id, title="Jardines", stage="reunion", max_stage=stage_index("reunion"),
                      owner_id=users["ventas"].id)
    db.add(opp)
    db.commit()
    return {"museo": museo, "tical": tical, "ajena": ajena, "ana": ana, "pedro": pedro, "intrusa": intrusa,
            "opp": opp, "other_seller": other_seller}


def quote_payload(number, **extra):
    data = {"numero_cotizacion": number, "fecha_emision": TODAY.isoformat(), "cliente_nombre": "X",
            "cliente_datos": {"name": "X"}, "moneda": "CRC", "total": 1000, "items": []}
    data.update(extra)
    return data


# --- Quote tool ------------------------------------------------------------------------

def test_client_only_sees_its_own_quotes(login_as, world):
    client = login_as("client")
    numbers = [q["numero_cotizacion"] for q in client.get("/api/quotes/").json()]
    assert numbers == ["Q-MUSEO"]
    tical_id = next(q["id"] for q in login_as("admin").get("/api/quotes/").json() if q["numero_cotizacion"] == "Q-TICAL")
    assert client.get(f"/api/quotes/{tical_id}").status_code == 404


def test_client_quotes_go_to_its_account_and_cannot_overwrite_others(db, login_as, world):
    client = login_as("client")
    assert client.post("/api/quotes/", json=quote_payload("Q-NUEVA")).status_code == 200
    assert db.query(Quote).filter_by(numero_cotizacion="Q-NUEVA").one().account_id == world["museo"].id
    assert client.post("/api/quotes/", json=quote_payload("Q-TICAL", total=1)).status_code == 403
    db.expire_all()
    assert db.query(Quote).filter_by(numero_cotizacion="Q-TICAL").one().total == 20


def test_client_quote_tool_has_no_account_picker(login_as, world):
    assert "accountPicker" not in login_as("client").get("/cotizador").text
    assert "accountPicker" in login_as("ventas").get("/cotizador").text


@pytest.mark.parametrize("role", ["admin", "ventas"])
def test_admin_and_ventas_must_pick_an_account(role, login_as, world):
    response = login_as(role).post("/api/quotes/", json=quote_payload("Q-SIN-CUENTA"))
    assert response.status_code == 400 and "Elija la cuenta" in response.json()["detail"]


def test_quote_from_an_opportunity_moves_it_to_proposal(db, login_as, world):
    opp = world["opp"]
    response = login_as("ventas").post("/api/quotes/", json=quote_payload(
        "Q-OPP", account_id=world["tical"].id, opportunity_id=opp.id))
    assert response.status_code == 200
    db.refresh(opp)
    assert opp.stage == "propuesta"
    assert db.query(CrmActivity).filter_by(opportunity_id=opp.id, type="cambio_etapa").count() == 1
    quote = db.query(Quote).filter_by(numero_cotizacion="Q-OPP").one()
    assert (quote.account_id, quote.opportunity_id) == (world["tical"].id, opp.id)
    history = login_as("ventas").get("/api/quotes/").json()
    assert next(q for q in history if q["numero_cotizacion"] == "Q-OPP")["account_name"] == "Tical"


def test_opportunity_must_belong_to_the_account(login_as, world):
    response = login_as("admin").post("/api/quotes/", json=quote_payload(
        "Q-MAL", account_id=world["museo"].id, opportunity_id=world["opp"].id))
    assert response.status_code == 400


# --- Account picker API -----------------------------------------------------------------

def test_picker_search_and_create_with_similar_warning(db, login_as, world):
    ventas = login_as("ventas")
    found = ventas.get("/clientes/api/cuentas?q=tic").json()
    assert found[0]["name"] == "Tical" and {c["name"] for c in found[0]["contacts"]} == {"Ana", "Pedro"}
    response = ventas.post("/clientes/api/cuentas", json={"name": "Tical S.A."})
    assert response.status_code == 409 and response.json()["similar"][0]["name"] == "Tical"
    created = ventas.post("/clientes/api/cuentas", json={"name": "Tical S.A.", "confirm": True}).json()
    assert db.get(Account, created["id"]).owner_id is not None


def test_picker_api_is_only_for_admin_and_ventas(login_as, world):
    for role in ["client", "supervisor", "worker"]:
        assert login_as(role).get("/clientes/api/cuentas?q=a").status_code == 403


def test_ventas_cannot_add_contacts_to_someone_elses_account(login_as, world):
    response = login_as("ventas").post(f"/clientes/api/cuentas/{world['ajena'].id}/contactos", json={"name": "X"})
    assert response.status_code == 403


# --- Projects --------------------------------------------------------------------------------

def project_payload(name, **extra):
    data = {"name": name, "client_ids": [], "worker_ids": [], "supplies": [], "tasks": [], "locations": [],
            "budget_lines": []}
    data.update(extra)
    return data


def test_project_needs_an_account(login_as, world):
    response = login_as("admin").post("/projects/new", json=project_payload("Sin cuenta"))
    assert response.status_code == 400 and "Elija la cuenta" in response.json()["detail"]


def test_project_takes_contacts_from_its_account(db, login_as, world):
    roles = [{"contact_id": world["ana"].id, "is_site": True, "receives_reports": True, "position": "Gerente"},
             {"contact_id": world["pedro"].id, "is_site": True, "receives_reports": False},
             {"contact_id": world["intrusa"].id, "is_site": True, "receives_reports": True}]  # other account: ignored
    response = login_as("admin").post("/projects/new", json=project_payload(
        "Tical Oficinas", account_id=world["tical"].id, contact_roles=roles, client_display_name="texto viejo"))
    assert response.status_code == 200, response.text
    project = db.query(Project).filter_by(name="Tical Oficinas").one()
    assert project.account_id == world["tical"].id and project.client_display_name == "Tical"
    saved = {r.contact_id: r for r in db.query(ProjectContactRole).filter_by(project_id=project.id)}
    assert set(saved) == {world["ana"].id, world["pedro"].id}
    assert saved[world["ana"].id].receives_reports and saved[world["ana"].id].position == "Gerente"


def test_editing_keeps_the_old_contact_list_as_history(db, login_as, world, users):
    project = db.get(Project, users["project_id"])
    db.add(ProjectContact(project_id=project.id, name="Contacto viejo", email="viejo@x.cr"))
    db.commit()
    response = login_as("admin").post(f"/projects/{project.id}/edit", json=project_payload(
        project.name, account_id=world["tical"].id,
        contact_roles=[{"contact_id": world["ana"].id, "is_site": True, "receives_reports": True}]))
    assert response.status_code == 200, response.text
    assert db.query(ProjectContact).filter_by(project_id=project.id).count() == 1
    assert db.query(ProjectContactRole).filter_by(project_id=project.id).count() == 1


def test_project_page_and_log_email_use_the_account_contacts(db, login_as, world, users):
    project = db.get(Project, users["project_id"])
    project.account_id = world["tical"].id
    db.add_all([ProjectContactRole(project_id=project.id, contact_id=world["ana"].id, is_site=True, receives_reports=True),
                ProjectContactRole(project_id=project.id, contact_id=world["pedro"].id, is_site=True, receives_reports=False),
                ProjectContact(project_id=project.id, name="Contacto viejo", email="viejo@x.cr")])
    log = DailyLog(project_id=project.id, user_id=users["admin"].id, date=TODAY)
    db.add(log)
    db.commit()
    admin = login_as("admin")
    page = admin.get(f"/projects/{project.id}").text
    assert "Ana" in page and "Pedro" in page and "Contacto viejo" not in page
    recipients = admin.get(f"/logs/{log.id}/detail").json()["project_contacts"]
    assert [r["email"] for r in recipients] == ["ana@tical.cr"]


def test_old_projects_without_roles_keep_their_contacts(db, login_as, users):
    project = db.get(Project, users["project_id"])
    db.add(ProjectContact(project_id=project.id, name="Contacto viejo", email="viejo@x.cr"))
    log = DailyLog(project_id=project.id, user_id=users["admin"].id, date=TODAY)
    db.add(log)
    db.commit()
    recipients = login_as("admin").get(f"/logs/{log.id}/detail").json()["project_contacts"]
    assert [r["email"] for r in recipients] == ["viejo@x.cr"]


def test_project_form_prefills_the_account_of_a_won_opportunity(login_as, world):
    html = login_as("admin").get(f"/projects/new?opportunity_id={world['opp'].id}").text
    assert '"name": "Tical"' in html and "oportunidad ganada" in html


# --- Win ------------------------------------------------------------------------------------

def test_creating_the_project_wins_the_opportunity(db, login_as, world):
    opp = world["opp"]
    login_as("admin").post("/projects/new", json=project_payload(
        "Tical Jardines", account_id=world["tical"].id, opportunity_id=opp.id))
    db.refresh(opp)
    project = db.query(Project).filter_by(name="Tical Jardines").one()
    assert opp.stage == "ganado" and opp.project_id == project.id and project.opportunity_id == opp.id


def test_link_an_existing_project_as_won(db, login_as, world, users):
    opp = world["opp"]
    response = login_as("admin").post(f"/clientes/oportunidades/{opp.id}/ganada",
                                      data={"project_id": str(users["project_id"])}, follow_redirects=False)
    assert response.status_code == 303
    db.refresh(opp)
    assert opp.stage == "ganado" and db.get(Project, users["project_id"]).account_id == world["tical"].id


def test_cannot_win_with_a_project_of_another_account(db, login_as, world, users):
    db.get(Project, users["project_id"]).account_id = world["museo"].id
    db.commit()
    login_as("admin").post(f"/clientes/oportunidades/{world['opp'].id}/ganada", data={"project_id": str(users["project_id"])})
    db.refresh(world["opp"])
    assert world["opp"].stage == "reunion"


def test_only_admin_marks_won(login_as, world, users):
    response = login_as("ventas").post(f"/clientes/oportunidades/{world['opp'].id}/ganada",
                                       data={"project_id": str(users["project_id"])}, follow_redirects=False)
    assert response.status_code == 403


def test_opportunity_page_actions(login_as, world):
    url = f"/clientes/oportunidades/{world['opp'].id}"
    assert f"/cotizador?opportunity_id={world['opp'].id}" in login_as("ventas").get(url).text
    assert "Marcar ganada" not in login_as("ventas").get(url).text
    assert "Marcar ganada" in login_as("admin").get(url).text


# --- Renewals ----------------------------------------------------------------------------------

@pytest.fixture
def contracts(db, world, users):
    soon = Project(name="Contrato pronto", account_id=world["tical"].id, is_active=True)
    later = Project(name="Contrato en 80 días", account_id=world["tical"].id, is_active=True)
    far = Project(name="Contrato lejano", account_id=world["tical"].id, is_active=True)
    theirs = Project(name="Contrato ajeno", account_id=world["ajena"].id, is_active=True)
    db.add_all([soon, later, far, theirs])
    db.flush()
    for project, days in [(soon, 30), (later, 80), (far, 200), (theirs, 20)]:
        db.add(ProjectBudget(project_id=project.id, end_date=TODAY + timedelta(days=days)))
    db.commit()
    return {"soon": soon, "later": later, "theirs": theirs}


def test_expiring_contracts_window(db, contracts):
    rows = {r["project"].name: r for r in expiring_contracts(db)}
    assert set(rows) == {"Contrato pronto", "Contrato en 80 días", "Contrato ajeno"}
    assert rows["Contrato pronto"]["urgent"] and not rows["Contrato en 80 días"]["urgent"]


def test_create_renewal_once(db, login_as, contracts, world, users):
    ventas = login_as("ventas")
    url = f"/clientes/proyectos/{contracts['soon'].id}/renovacion"
    assert ventas.post(url, follow_redirects=False).status_code == 303
    assert ventas.post(url, follow_redirects=False).status_code == 303
    renewals = db.query(Opportunity).filter_by(kind="renovacion", project_id=contracts["soon"].id).all()
    assert len(renewals) == 1 and renewals[0].owner_id == users["ventas"].id
    assert "Renovación en curso" in ventas.get("/clientes").text


def test_ventas_cannot_renew_someone_elses_contract(login_as, contracts):
    response = login_as("ventas").post(f"/clientes/proyectos/{contracts['theirs'].id}/renovacion", follow_redirects=False)
    assert response.status_code == 403


def test_expiring_list_on_the_funnel(login_as, contracts):
    html = login_as("ventas").get("/clientes").text
    assert "Contratos por vencer" in html and "Contrato pronto" in html and "Crear renovación" in html
