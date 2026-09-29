"""Fase 2B: Clientes (funnel, accounts, file, opportunities, follow-ups) and permissions."""
from datetime import date, timedelta

import pytest

from app.db.models.activity import ActivityLog
from app.db.models.crm import Account, Contact, CrmActivity, CrmGoal, Opportunity, stage_index
from app.db.models.project import Project
from app.db.models.quote import Quote
from app.utils.crm import funnel, next_steps, quote_amount
from tests.conftest import login, make_user, new_client

TODAY = date.today()


@pytest.fixture
def crm(db, users):
    """An account owned by u_ventas, one owned by another seller, and an unowned one."""
    other = make_user(db, "otra_ventas", "ventas", full_name="Otra Vendedora")
    mine = Account(name="Hotel Playa Azul", kind="hotel", owner_id=users["ventas"].id)
    theirs = Account(name="Condominio Ajeno", owner_id=other.id)
    free = Account(name="Empresa Sin Dueño")
    db.add_all([mine, theirs, free])
    db.flush()
    opp_mine = Opportunity(account_id=mine.id, title="Jardines 2027", motor="mantenimiento", stage="reunion",
                           max_stage=stage_index("reunion"), owner_id=users["ventas"].id,
                           next_step="Llamar", next_step_date=TODAY - timedelta(days=2))
    opp_theirs = Opportunity(account_id=theirs.id, title="Regalos fin de año", motor="regalo_corporativo",
                             stage="propuesta", max_stage=stage_index("propuesta"), owner_id=other.id,
                             next_step="Enviar", next_step_date=TODAY)
    db.add_all([opp_mine, opp_theirs, Contact(account_id=mine.id, name="Marta", email="marta@playa.cr", is_primary=True)])
    project = db.get(Project, users["project_id"])
    project.account_id = mine.id
    db.commit()
    return {"mine": mine, "theirs": theirs, "free": free, "opp_mine": opp_mine, "opp_theirs": opp_theirs,
            "other": other}


# --- Access ------------------------------------------------------------------------

PAGES = ["/clientes", "/clientes/cuentas", "/clientes/cuentas/nueva", "/clientes/cuentas/{mine}",
         "/clientes/oportunidades/{opp}"]


@pytest.mark.parametrize("path", PAGES)
@pytest.mark.parametrize("role,expected", [("admin", 200), ("ventas", 200), ("supervisor", 403), ("worker", 403),
                                           ("client", 403)])
def test_clientes_pages_access(role, expected, path, login_as, crm):
    url = path.format(mine=crm["mine"].id, opp=crm["opp_mine"].id)
    assert login_as(role).get(url, follow_redirects=False).status_code == expected


@pytest.mark.parametrize("role,visible", [("admin", True), ("ventas", True), ("supervisor", False), ("worker", False),
                                          ("client", False)])
def test_menu_link(role, visible, login_as, users):
    assert ('href="/clientes"' in login_as(role).get("/dashboard/").text) is visible


def test_ventas_sees_every_account_but_no_finances(login_as, crm, users):
    ventas = login_as("ventas")
    listing = ventas.get("/clientes/cuentas").text
    assert all(name in listing for name in ["Hotel Playa Azul", "Condominio Ajeno", "Empresa Sin Dueño"])
    page = ventas.get(f"/clientes/cuentas/{crm['mine'].id}").text
    assert "Proyecto de prueba" in page and "/finance/" not in page
    assert f"/finance/{users['project_id']}" in login_as("admin").get(f"/clientes/cuentas/{crm['mine'].id}").text


# --- Editing rules for ventas --------------------------------------------------------

def post(client, url, data):
    return client.post(url, data=data, follow_redirects=False)


@pytest.mark.parametrize("action", ["editar", "contactos", "oportunidades", "seguimientos"])
def test_ventas_cannot_touch_someone_elses_account(action, login_as, crm):
    data = {"editar": {"name": "X"}, "contactos": {"name": "X"}, "oportunidades": {"title": "X"},
            "seguimientos": {"type": "llamada"}}[action]
    response = post(login_as("ventas"), f"/clientes/cuentas/{crm['theirs'].id}/{action}", data)
    assert response.status_code == 403


def test_ventas_cannot_change_someone_elses_opportunity(login_as, crm):
    ventas = login_as("ventas")
    assert post(ventas, f"/clientes/oportunidades/{crm['opp_theirs'].id}/etapa", {"stage": "ganado"}).status_code == 403
    assert post(ventas, f"/clientes/oportunidades/{crm['opp_theirs'].id}/editar", {"title": "X"}).status_code == 403
    assert "Solo lectura" in ventas.get(f"/clientes/oportunidades/{crm['opp_theirs'].id}").text


def test_ventas_claims_an_unowned_account_by_editing_it(db, login_as, crm, users):
    post(login_as("ventas"), f"/clientes/cuentas/{crm['free'].id}/contactos", {"name": "Luis", "email": "LUIS@x.cr"})
    db.refresh(crm["free"])
    assert crm["free"].owner_id == users["ventas"].id
    assert crm["free"].contacts[0].email == "luis@x.cr"


@pytest.mark.parametrize("url,data", [
    ("/clientes/cuentas/{mine}/duenio", {"owner_id": ""}),
    ("/clientes/metas", {"prospecto": "1", "respuesta": "1", "reunion": "1", "propuesta": "1", "ganado": "1"}),
])
def test_admin_only_actions(url, data, login_as, crm):
    assert post(login_as("ventas"), url.format(mine=crm["mine"].id), data).status_code == 403
    assert post(login_as("admin"), url.format(mine=crm["mine"].id), data).status_code == 303


def test_admin_reassigns_owner(db, login_as, crm):
    post(login_as("admin"), f"/clientes/cuentas/{crm['mine'].id}/duenio", {"owner_id": str(crm["other"].id)})
    db.refresh(crm["mine"])
    assert crm["mine"].owner_id == crm["other"].id


def test_discard_only_by_owner_or_admin(db, login_as, crm):
    assert post(login_as("ventas"), f"/clientes/cuentas/{crm['theirs'].id}/descartar", {}).status_code == 403
    post(login_as("ventas"), f"/clientes/cuentas/{crm['mine'].id}/descartar", {"reason": "No le interesa"})
    db.refresh(crm["mine"])
    assert crm["mine"].discarded_at is not None
    post(login_as("ventas"), f"/clientes/cuentas/{crm['mine'].id}/descartar", {})
    db.refresh(crm["mine"])
    assert crm["mine"].discarded_at is None


# --- New account and duplicates --------------------------------------------------------

def test_new_account_warns_about_similar_ones(db, login_as, crm, users):
    ventas = login_as("ventas")
    response = post(ventas, "/clientes/cuentas/nueva", {"name": "Hotel Playa Azul S.A.", "kind": "hotel"})
    assert response.status_code == 200 and "Ya hay una cuenta parecida" in response.text
    assert db.query(Account).filter(Account.name == "Hotel Playa Azul S.A.").count() == 0

    response = post(ventas, "/clientes/cuentas/nueva", {"name": "Otro Nombre", "contact_email": "marta@playa.cr"})
    assert "Hotel Playa Azul" in response.text  # same contact email

    response = post(ventas, "/clientes/cuentas/nueva", {"name": "Hotel Playa Azul S.A.", "confirm": "true",
                                                        "contact_name": "Ana", "contact_email": "ana@x.cr"})
    assert response.status_code == 303
    created = db.query(Account).filter(Account.name == "Hotel Playa Azul S.A.").one()
    assert created.owner_id == users["ventas"].id and created.contacts[0].is_primary


def test_same_tax_id_is_never_created_twice(db, login_as, crm):
    crm["mine"].tax_id = "3-101-123456"
    db.commit()
    response = post(login_as("admin"), "/clientes/cuentas/nueva",
                    {"name": "Nombre Distinto", "tax_id": "3-101-123456", "confirm": "true"})
    assert response.status_code == 200 and "cédula ya está registrada" in response.text
    assert db.query(Account).filter(Account.name == "Nombre Distinto").count() == 0


# --- Stages, funnel and amounts -----------------------------------------------------------

def test_stage_change_records_followup_and_audit(db, login_as, crm):
    opp = crm["opp_mine"]
    post(login_as("ventas"), f"/clientes/oportunidades/{opp.id}/etapa", {"stage": "propuesta"})
    db.refresh(opp)
    assert opp.stage == "propuesta" and opp.max_stage == stage_index("propuesta")
    change = db.query(CrmActivity).filter_by(opportunity_id=opp.id, type="cambio_etapa").one()
    assert change.notes == "Reunión → Propuesta"
    assert db.query(ActivityLog).filter_by(entity_type="OPPORTUNITY", entity_id=opp.id).count() == 1


def test_lost_needs_a_reason_and_keeps_the_highest_stage(db, login_as, crm):
    opp = crm["opp_mine"]
    ventas = login_as("ventas")
    post(ventas, f"/clientes/oportunidades/{opp.id}/etapa", {"stage": "perdido"})
    db.refresh(opp)
    assert opp.stage == "reunion"
    post(ventas, f"/clientes/oportunidades/{opp.id}/etapa", {"stage": "perdido", "lost_reason": "Presupuesto"})
    db.refresh(opp)
    assert opp.stage == "perdido" and opp.max_stage == stage_index("reunion") and opp.lost_reason == "Presupuesto"


def test_funnel_counts_accounts_by_highest_stage(db, crm):
    # A second, lost opportunity on the same account doesn't count it twice.
    db.add(Opportunity(account_id=crm["mine"].id, title="Perdida", stage="perdido", max_stage=stage_index("respuesta")))
    db.commit()
    rows = {r["stage"]: r for r in funnel(db)}
    assert [rows[s]["reached"] for s in ["prospecto", "respuesta", "reunion", "propuesta", "ganado"]] == [2, 2, 2, 1, 0]
    # Only Propuesta and Ganado have a target; the other boxes show the share from the previous one.
    assert [rows[s]["target"] for s in ["prospecto", "respuesta", "reunion", "propuesta", "ganado"]] == [0, 0, 0, 10, 4]
    assert rows["prospecto"]["from_previous"] is None and rows["respuesta"]["from_previous"] == 100
    assert rows["propuesta"]["from_previous"] == 50 and rows["ganado"]["from_previous"] == 0
    assert {r["stage"]: r["reached"] for r in funnel(db, motor="mantenimiento")}["propuesta"] == 0


def test_goals_are_editable(db, login_as, crm):
    post(login_as("admin"), "/clientes/metas", {"prospecto": "200", "respuesta": "80", "reunion": "30",
                                                "propuesta": "12", "ganado": "5"})
    assert db.get(CrmGoal, "propuesta").target == 12 and db.get(CrmGoal, "ganado").target == 5
    assert db.get(CrmGoal, "prospecto") is None  # the earlier stages have no target
    html = login_as("admin").get("/clientes").text
    assert "/ 12" in html and "/ 5" in html and "de Nueva" in html
    post(login_as("admin"), "/clientes/metas", {"propuesta": "", "ganado": "6"})
    assert db.get(CrmGoal, "propuesta").target == 0  # empty = no target


def test_amount_comes_from_the_linked_quote(db, crm):
    opp = crm["opp_theirs"]
    opp.amount_crc = 100
    db.commit()
    assert quote_amount(db, opp) == 100
    db.add(Quote(numero_cotizacion="Q-1", fecha_emision=TODAY, cliente_nombre="X", moneda="CRC", total=750000,
                 opportunity_id=opp.id))
    db.commit()
    assert quote_amount(db, opp) == 750000


def test_next_steps_and_dashboard(db, login_as, crm, users):
    steps = next_steps(db)
    assert [o.title for o in steps["vencidos"]] == ["Jardines 2027"]
    assert [o.title for o in steps["hoy"]] == ["Regalos fin de año"]
    mine = next_steps(db, owner_id=users["ventas"].id)
    assert mine["hoy"] == [] and len(mine["vencidos"]) == 1

    html = login_as("ventas").get("/dashboard/").text
    assert "Mis próximos pasos" in html and "Hotel Playa Azul" in html and "Condominio Ajeno" not in html
    assert "Filtro comercial del equipo" in login_as("admin").get("/dashboard/").text


# --- Follow-ups ------------------------------------------------------------------------

def test_followup_updates_the_next_step(db, login_as, crm):
    opp = crm["opp_mine"]
    response = post(login_as("ventas"), f"/clientes/cuentas/{crm['mine'].id}/seguimientos", {
        "type": "llamada", "notes": "Pidió propuesta", "opportunity_id": str(opp.id),
        "next_step": "Enviar propuesta", "next_step_date": (TODAY + timedelta(days=3)).isoformat()})
    assert response.status_code == 303
    db.refresh(opp)
    assert opp.next_step == "Enviar propuesta" and opp.next_step_date == TODAY + timedelta(days=3)
    followup = db.query(CrmActivity).filter_by(account_id=crm["mine"].id, type="llamada").one()
    assert followup.notes == "Pidió propuesta" and followup.opportunity_id == opp.id


def test_followup_rejects_future_dates_and_foreign_opportunities(db, login_as, crm):
    ventas = login_as("ventas")
    post(ventas, f"/clientes/cuentas/{crm['mine'].id}/seguimientos",
         {"type": "nota", "happened_at": (TODAY + timedelta(days=1)).isoformat()})
    post(ventas, f"/clientes/cuentas/{crm['mine'].id}/seguimientos",
         {"type": "nota", "opportunity_id": str(crm["opp_theirs"].id)})
    post(ventas, f"/clientes/cuentas/{crm['mine'].id}/seguimientos", {"type": "cambio_etapa"})
    assert db.query(CrmActivity).count() == 0


def test_merged_account_redirects_to_the_one_that_stayed(db, login_as, crm):
    crm["free"].merged_into_id = crm["mine"].id
    db.commit()
    response = login_as("admin").get(f"/clientes/cuentas/{crm['free'].id}", follow_redirects=False)
    assert response.status_code == 303 and response.headers["location"] == f"/clientes/cuentas/{crm['mine'].id}"
