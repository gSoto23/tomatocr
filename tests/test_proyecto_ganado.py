"""A project that came in without an opportunity (a tender won in SICOP) is registered as won
in Clientes from the project form, so it counts in the goals."""
from datetime import date, timedelta

import pytest

from app.db.models.crm import Account, CrmActivity, Opportunity
from app.db.models.project import Project
from app.utils.crm import FunnelPeriod, create_renewal, money_progress

TODAY = date.today()


@pytest.fixture
def muni(db, users):
    account = Account(name="Municipalidad de Alajuela", owner_id=users["admin"].id)
    db.add(account)
    db.commit()
    return account


def payload(name, account, **extra):
    data = {"name": name, "account_id": account.id, "client_ids": [], "worker_ids": [], "supplies": [],
            "tasks": [], "locations": [], "budget_lines": []}
    data.update(extra)
    return data


def won_of(db, project):
    return db.query(Opportunity).filter(Opportunity.project_id == project.id).all()


def test_new_tender_project_registered_as_won_counts_in_the_goals(db, login_as, users, muni):
    response = login_as("admin").post("/projects/new", json=payload(
        "Cámaras Trampa", muni, licitation_number="2026LD-000123", register_won=True,
        won_motor="sector_publico", won_origin="sicop",
        budget_lines=[{"name": "Cámaras", "subtotal": 1000000, "tax_percentage": 13}]))
    assert response.status_code == 200
    project = db.query(Project).filter_by(name="Cámaras Trampa").one()
    [opp] = won_of(db, project)
    assert (opp.stage, opp.motor, opp.origin, opp.kind, opp.source) == ("ganado", "sector_publico", "sicop", "nuevo", "proyecto")
    assert opp.title == "Cámaras Trampa" and opp.account_id == muni.id and project.opportunity_id == opp.id
    assert opp.won_at is not None and opp.owner_id == users["admin"].id
    assert db.query(CrmActivity).filter_by(opportunity_id=opp.id, type="nota").count() == 1
    period = FunnelPeriod("Prueba", TODAY - timedelta(days=1), TODAY + timedelta(days=1))
    tenders = next(row for row in money_progress(db, period) if row["key"] == "monto_licitaciones")
    assert (tenders["count"], round(tenders["won"])) == (1, 1130000)


def test_kind_follows_the_account_unless_chosen(db, login_as, muni):
    admin = login_as("admin")
    admin.post("/projects/new", json=payload("Primero", muni, register_won=True))
    admin.post("/projects/new", json=payload("Segundo", muni, register_won=True))
    admin.post("/projects/new", json=payload("Tercero", muni, register_won=True, won_kind="nuevo"))
    kinds = {p.name: won_of(db, p)[0].kind for p in db.query(Project).filter(Project.account_id == muni.id)}
    assert kinds == {"Primero": "nuevo", "Segundo": "ampliacion", "Tercero": "nuevo"}


def test_without_the_box_no_opportunity_is_created(db, login_as, muni):
    login_as("admin").post("/projects/new", json=payload("Sin metas", muni, licitation_number="2026LD-1"))
    assert db.query(Opportunity).count() == 0


def test_unknown_motor_or_origin_is_left_empty(db, login_as, muni):
    login_as("admin").post("/projects/new", json=payload("Raro", muni, register_won=True, won_motor="x", won_origin="y"))
    opp = db.query(Opportunity).one()
    assert (opp.motor, opp.origin) == (None, None)


def test_existing_project_registered_as_won_only_once(db, login_as, users, muni):
    admin = login_as("admin")
    project_id = users["project_id"]
    url = f"/projects/{project_id}/edit"
    assert admin.post(url, json=payload("Proyecto viejo", muni, register_won=True, won_motor="sector_publico")).status_code == 200
    again = admin.post(url, json=payload("Proyecto viejo", muni, register_won=True))
    assert again.status_code == 400 and "ya tiene" in again.json()["detail"]
    assert len(won_of(db, db.get(Project, project_id))) == 1


def test_an_open_renewal_does_not_count_as_won(db, login_as, users, muni):
    project = db.get(Project, users["project_id"])
    project.account_id = muni.id
    create_renewal(db, project, users["admin"])
    db.commit()
    html = login_as("admin").get(f"/projects/{project.id}/edit").text
    assert "Registrar como ganado en Clientes" in html
    login_as("admin").post(f"/projects/{project.id}/edit", json=payload(project.name, muni, register_won=True))
    assert db.query(Opportunity).filter_by(project_id=project.id, stage="ganado").count() == 1


def test_form_shows_the_box_or_the_linked_opportunity(db, login_as, users, muni):
    admin = login_as("admin")
    assert "Registrar como ganado en Clientes" in admin.get("/projects/new").text
    admin.post(f"/projects/{users['project_id']}/edit", json=payload("Proyecto viejo", muni, register_won=True))
    opp = db.query(Opportunity).one()
    html = admin.get(f"/projects/{users['project_id']}/edit").text
    assert "Registrar como ganado en Clientes" not in html
    assert f"/clientes/oportunidades/{opp.id}" in html and "data-won-linked" in html


def test_project_from_an_opportunity_has_no_box(db, login_as, muni):
    opp = Opportunity(account_id=muni.id, title="Desde Clientes", stage="propuesta")
    db.add(opp)
    db.commit()
    assert "data-won-section" not in login_as("admin").get(f"/projects/new?opportunity_id={opp.id}").text
