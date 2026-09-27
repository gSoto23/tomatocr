"""Fase 2A: accounts from current clients, duplicates and merge (docs/DISENO_CRM.md)."""
from datetime import date, timedelta

import pytest

from app.db.models.activity import ActivityLog
from app.db.models.crm import Account, Contact, Opportunity
from app.db.models.project import Project
from app.db.models.quote import Quote
from app.db.models.reforestation import ReforestationProject
from app.utils.crm import backfill, find_duplicates, looks_like_tax_id, merge_accounts, normalize_name, similarity
from tests.conftest import make_user

TODAY = date(2026, 9, 27)


def test_normalize_name():
    assert normalize_name("Tical S.A.") == "tical"
    assert normalize_name("  TICAL, sociedad anónima ") == "tical"
    assert normalize_name("Jardines Museo de Arte Costarricense") == "jardines museo de arte costarricense"
    assert normalize_name("Casa Guácima - González Baccaglio") == "casa guacima gonzalez baccaglio"
    assert normalize_name("Casa") == "casa"  # "sa" only as a separate suffix


def test_similarity_and_tax_id():
    assert similarity("Municipalidad Alajuela", "Municipalidad de Alajuela") >= 0.85
    assert similarity("Tical", "Isidro Viquez") < 0.85
    assert looks_like_tax_id("3-101-876296") and looks_like_tax_id("112340567")
    assert not looks_like_tax_id("María Pérez")


@pytest.fixture
def owner(db):
    return make_user(db, "gerardo", "admin", full_name="Gerardo Soto")


@pytest.fixture
def data(db, users):
    """users fixture: project with u_client assigned. Plus other sources of clients."""
    client = users["client"]
    client.full_name, client.email, client.phone = "Museo de Arte", "museo@example.cr", "8888-0000"
    tical = Project(name="Tical - Paisajismo", client_display_name="Tical S.A.",
                    contact_name="Ana Rojas", contact_email="ana@tical.cr")
    muni = Project(name="Arborización Alajuela", client_display_name="Municipalidad de Alajuela")
    quotes = [
        Quote(numero_cotizacion="C-1", fecha_emision=TODAY - timedelta(days=10), cliente_nombre="TICAL",
              cliente_datos={"id": "Ana Rojas", "email": "ana@tical.cr"}, moneda="CRC", total=500000),
        Quote(numero_cotizacion="C-2", fecha_emision=TODAY - timedelta(days=20), cliente_nombre="Hotel Playa Azul",
              cliente_datos={"id": "3-101-123456", "email": "compras@playa.cr", "phone": "2222-1111"},
              moneda="CRC", total=1250000),
        Quote(numero_cotizacion="C-3", fecha_emision=TODAY - timedelta(days=120), cliente_nombre="Condominio Viejo",
              cliente_datos={}, moneda="CRC", total=100),
        Quote(numero_cotizacion="C-4", fecha_emision=TODAY - timedelta(days=5), cliente_nombre="Empresa Dólares",
              cliente_datos={"id": "Luis"}, moneda="USD", total=900),
    ]
    reforestation = ReforestationProject(client_name="Municipalidad Alajuela")
    db.add_all([tical, muni, reforestation, *quotes])
    db.commit()
    return {"tical": tical, "muni": muni, "reforestation": reforestation, "quotes": quotes}


def accounts_by_name(db):
    return {a.name: a for a in db.query(Account).filter(Account.merged_into_id.is_(None))}


def test_backfill_covers_every_client_project_and_quote(db, owner, users, data):
    report = backfill(db, owner, today=TODAY)
    db.commit()
    accounts = accounts_by_name(db)
    assert set(accounts) == {"Museo de Arte", "Tical S.A.", "Municipalidad de Alajuela", "Hotel Playa Azul",
                             "Condominio Viejo", "Empresa Dólares", "Municipalidad Alajuela"}

    # Every project, quote and reforestation project ends up linked.
    assert db.query(Project).filter(Project.account_id.is_(None)).count() == 0
    assert db.query(Quote).filter(Quote.account_id.is_(None)).count() == 0
    assert db.query(ReforestationProject).filter(ReforestationProject.account_id.is_(None)).count() == 0

    # 1. Client user -> account with a contact linked to the portal user; project linked through it.
    museo = accounts["Museo de Arte"]
    assert db.get(Project, users["project_id"]).account_id == museo.id
    assert [c.user_id for c in museo.contacts] == [users["client"].id]

    # 2 and 3. Project and quote with the same normalized name share the account and contact.
    tical = accounts["Tical S.A."]
    assert data["quotes"][0].account_id == tical.id
    assert [c.email for c in tical.contacts] == ["ana@tical.cr"]

    # Quote "id" that looks like a cédula becomes the tax id; otherwise it's the contact's name.
    assert accounts["Hotel Playa Azul"].tax_id == "3-101-123456"
    assert accounts["Empresa Dólares"].tax_id is None
    assert accounts["Empresa Dólares"].contacts[0].name == "Luis"

    # 5. Status and kind.
    assert {tical.status, museo.status, accounts["Municipalidad Alajuela"].status} == {"cliente"}
    assert accounts["Hotel Playa Azul"].status == "prospecto"
    assert accounts["Municipalidad Alajuela"].kind == "institucion_publica"

    # 6. Recent prospect quotes -> opportunities in "propuesta"; old ones and client quotes don't.
    opportunities = {o.title: o for o in db.query(Opportunity)}
    assert set(opportunities) == {"Cotización C-2", "Cotización C-4"}
    assert opportunities["Cotización C-2"].stage == "propuesta" and opportunities["Cotización C-2"].amount_crc == 1250000
    assert opportunities["Cotización C-4"].amount_crc is None  # USD isn't copied as colones
    assert data["quotes"][1].opportunity_id == opportunities["Cotización C-2"].id

    # 7. Owner and duplicates for review (not merged automatically).
    assert {a.owner_id for a in accounts.values()} == {owner.id}
    assert report.counts["posible duplicado"] == 1
    dup = [r for r in report.rows if r["accion"] == "posible duplicado"][0]
    assert {dup["cuenta"], dup["detalle"].split(" (")[0]} == {"Municipalidad de Alajuela", "Municipalidad Alajuela"}


def test_backfill_twice_adds_nothing(db, owner, users, data):
    backfill(db, owner, today=TODAY)
    db.commit()
    counts = (db.query(Account).count(), db.query(Contact).count(), db.query(Opportunity).count())
    report = backfill(db, owner, today=TODAY)
    db.commit()
    assert (db.query(Account).count(), db.query(Contact).count(), db.query(Opportunity).count()) == counts
    assert set(report.counts) <= {"posible duplicado"}


def test_dry_run_rolls_back_everything(db, owner, users, data):
    report = backfill(db, owner, today=TODAY)
    assert report.counts["cuenta nueva"] == 7
    db.rollback()
    assert db.query(Account).count() == 0
    assert db.query(Project).filter(Project.account_id.isnot(None)).count() == 0


def test_new_clients_after_a_backfill_are_picked_up(db, owner, users, data):
    backfill(db, owner, today=TODAY)
    db.commit()
    db.add(Project(name="Nuevo", client_display_name="tical sa"))
    db.commit()
    report = backfill(db, owner, today=TODAY)
    db.commit()
    assert report.counts.get("cuenta nueva", 0) == 0 and report.counts["proyecto ligado"] == 1


# --- Merge ------------------------------------------------------------------------

def test_merge_moves_everything_and_keeps_history(db, owner, users, data):
    backfill(db, owner, today=TODAY)
    db.commit()
    accounts = accounts_by_name(db)
    keep, drop = accounts["Municipalidad de Alajuela"], accounts["Municipalidad Alajuela"]
    drop.tax_id = "3-014-042063"
    db.commit()

    merge_accounts(db, keep, drop, owner)

    db.refresh(keep), db.refresh(drop)
    assert data["reforestation"].account_id == keep.id
    assert data["muni"].account_id == keep.id
    assert keep.tax_id == "3-014-042063" and drop.tax_id is None
    assert drop.merged_into_id == keep.id and drop.status == "inactivo"
    assert db.query(ActivityLog).filter_by(action="MERGE", entity_id=keep.id).count() == 1
    assert find_duplicates(db) == []


def test_merge_refuses_same_or_merged_accounts(db, owner, users, data):
    backfill(db, owner, today=TODAY)
    db.commit()
    a = accounts_by_name(db)["Tical S.A."]
    with pytest.raises(ValueError):
        merge_accounts(db, a, a, owner)


# --- Duplicates screen ---------------------------------------------------------------

@pytest.fixture
def backfilled(db, owner, users, data):
    backfill(db, owner, today=TODAY)
    db.commit()
    return accounts_by_name(db)


def test_duplicates_page_lists_the_pair(login_as, backfilled):
    html = login_as("admin").get("/crm/duplicados").text
    assert "Municipalidad Alajuela" in html and "Municipalidad de Alajuela" in html
    assert "Quedarse con" in html


@pytest.mark.parametrize("role", ["supervisor", "worker", "client", "ventas"])
def test_only_admin_reviews_duplicates(role, login_as, backfilled):
    client = login_as(role)
    keep, drop = backfilled["Municipalidad de Alajuela"], backfilled["Municipalidad Alajuela"]
    assert client.get("/crm/duplicados", follow_redirects=False).status_code == 403
    assert client.post(f"/crm/cuentas/{keep.id}/fusionar/{drop.id}", follow_redirects=False).status_code == 403
    assert client.post(f"/crm/duplicados/{keep.id}/{drop.id}/descartar", follow_redirects=False).status_code == 403


def test_merge_from_the_screen(db, login_as, backfilled, data):
    keep, drop = backfilled["Municipalidad de Alajuela"], backfilled["Municipalidad Alajuela"]
    response = login_as("admin").post(f"/crm/cuentas/{keep.id}/fusionar/{drop.id}", follow_redirects=False)
    assert response.status_code == 303
    db.expire_all()
    assert db.get(Account, drop.id).merged_into_id == keep.id
    assert db.get(ReforestationProject, data["reforestation"].id).account_id == keep.id


def test_dismissed_pair_is_not_shown_again(db, login_as, backfilled):
    admin = login_as("admin")
    keep, drop = backfilled["Municipalidad de Alajuela"], backfilled["Municipalidad Alajuela"]
    admin.post(f"/crm/duplicados/{drop.id}/{keep.id}/descartar")
    assert "No hay posibles duplicados" in admin.get("/crm/duplicados").text
    assert db.get(Account, drop.id).merged_into_id is None
