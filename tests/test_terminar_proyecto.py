"""Terminar un proyecto: the contract will not be renewed (leaves the renewal alert; can be reopened)."""
from datetime import timedelta

import pytest

from app.db.models.activity import ActivityLog
from app.db.models.crm import Account, Opportunity
from app.db.models.finance import ProjectBudget
from app.db.models.project import Project
from app.utils.crm import create_renewal, end_project, expiring_contracts
from app.utils.timecr import today_cr


@pytest.fixture
def contract(db, users):
    account = Account(name="Municipalidad", owner_id=users["ventas"].id)
    db.add(account)
    db.flush()
    project = Project(name="Cámaras trampa", account_id=account.id, is_active=True)
    db.add(project)
    db.flush()
    db.add(ProjectBudget(project_id=project.id, end_date=today_cr() + timedelta(days=4)))
    db.commit()
    return project


def alert(admin):
    return admin.get("/dashboard").text


def test_alert_offers_renew_and_terminate(login_as, contract):
    html = alert(login_as("admin"))
    assert "contrato por vencer sin renovación" in html
    assert f'action="/projects/{contract.id}/terminar"' in html
    assert f'action="/clientes/proyectos/{contract.id}/renovacion"' in html
    assert 'data-confirm-input="reason"' in html  # the system's window asks the optional reason
    assert '<input type="hidden" name="reason">' in html and 'data-confirm-input-maxlength="500"' in html


def test_terminate_from_the_alert(db, login_as, users, contract):
    admin = login_as("admin")
    response = admin.post(f"/projects/{contract.id}/terminar", data={"reason": "El cliente no tiene presupuesto",
                                                                      "next": "/dashboard"}, follow_redirects=False)
    assert response.status_code == 303 and response.headers["location"] == "/dashboard"
    db.refresh(contract)
    assert contract.ended_at is not None and contract.ended_by_id == users["admin"].id
    assert contract.end_reason == "El cliente no tiene presupuesto"
    assert contract.is_active  # the contract still runs until its end date
    assert expiring_contracts(db) == []
    html = alert(admin)
    assert "contrato por vencer sin renovación" not in html
    log = db.query(ActivityLog).filter_by(entity_type="PROJECT", entity_id=contract.id).one()
    assert "terminado" in log.details and "presupuesto" in log.details
    # A terminated project no longer offers the renewal.
    assert "Crear renovación" not in admin.get("/clientes").text
    with pytest.raises(ValueError):
        create_renewal(db, contract, users["admin"])
    renew = admin.post(f"/clientes/proyectos/{contract.id}/renovacion", follow_redirects=False)
    assert renew.status_code == 303 and renew.headers["location"] == "/clientes"
    assert db.query(Opportunity).filter_by(project_id=contract.id).count() == 0


def test_terminate_closes_the_open_renewal_as_lost(db, users, contract):
    renewal = create_renewal(db, contract, users["admin"])
    db.commit()
    closed = end_project(db, contract, users["admin"])
    db.commit()
    db.refresh(renewal)
    assert closed == [renewal] and renewal.stage == "perdido" and renewal.lost_reason == "No renovó"


def test_reason_is_optional_and_next_must_be_local(db, login_as, contract):
    response = login_as("admin").post(f"/projects/{contract.id}/terminar", data={"next": "https://evil.example"},
                                      follow_redirects=False)
    assert response.headers["location"] == f"/projects/{contract.id}"
    db.refresh(contract)
    assert contract.ended_at is not None and contract.end_reason is None


def test_reopen_brings_the_alert_back(db, login_as, contract):
    admin = login_as("admin")
    admin.post(f"/projects/{contract.id}/terminar", data={"reason": "x"})
    detail = admin.get(f"/projects/{contract.id}").text
    assert "Proyecto terminado" in detail and f'action="/projects/{contract.id}/reabrir"' in detail
    admin.post(f"/projects/{contract.id}/reabrir")
    db.refresh(contract)
    assert contract.ended_at is None and contract.end_reason is None and contract.ended_by_id is None
    assert "contrato por vencer sin renovación" in alert(admin)
    details = [l.details for l in db.query(ActivityLog).filter_by(entity_type="PROJECT", entity_id=contract.id)]
    assert any("reabierto" in d for d in details)


def test_only_admin_terminates(login_as, contract):
    for role in ("ventas", "supervisor", "worker"):
        assert login_as(role).post(f"/projects/{contract.id}/terminar").status_code == 403
        assert login_as(role).post(f"/projects/{contract.id}/reabrir").status_code == 403


def test_project_list_filter(db, login_as, users, contract):
    end_project(db, contract, users["admin"], "No renueva")
    db.commit()
    admin = login_as("admin")
    ended = admin.get("/projects?estado=terminados").text
    assert "Cámaras trampa" in ended and "Terminado" in ended
    assert "Cámaras trampa" not in admin.get("/projects?estado=activos").text
    assert "Cámaras trampa" in admin.get("/projects").text
