"""Pilot in the system: funnel period, only new opportunities count, admin assigns
opportunities (with an e-mail to the seller) and the team guide."""
from datetime import date, datetime, timedelta

import pytest

from app.db.models.activity import ActivityLog
from app.db.models.crm import Account, CrmSetting, Opportunity, stage_index
from app.routers import crm as crm_router
from app.utils.crm import FunnelPeriod, funnel, funnel_period
from tests.conftest import make_user

PILOT = FunnelPeriod("Piloto", date(2026, 10, 15), date(2026, 12, 15))


def opp(db, account, stage="prospecto", kind="nuevo", created=datetime(2026, 10, 20, 15), **fields):
    o = Opportunity(account_id=account.id, title=f"{account.name} {kind}", stage=stage, kind=kind,
                    max_stage=stage_index(stage) if stage != "perdido" else fields.pop("max_stage", 0),
                    created_at=created, **fields)
    db.add(o)
    db.commit()
    return o


def reached(rows):
    return [r["reached"] for r in rows]


@pytest.fixture
def accounts(db):
    names = ["Antes", "Dentro", "Renovacion", "Ampliacion", "Perdida", "Borde"]
    items = {n: Account(name=n) for n in names}
    db.add_all(items.values())
    db.commit()
    return items


def test_period_counts_only_new_opportunities_created_inside(db, accounts):
    opp(db, accounts["Antes"], "propuesta", created=datetime(2026, 9, 1))
    opp(db, accounts["Dentro"], "reunion")
    opp(db, accounts["Renovacion"], "propuesta", kind="renovacion")
    opp(db, accounts["Ampliacion"], "respuesta", kind="ampliacion")
    opp(db, accounts["Perdida"], "perdido", max_stage=stage_index("respuesta"))
    assert reached(funnel(db, period=PILOT)) == [2, 2, 1, 0, 0]
    assert reached(funnel(db)) == [5, 5, 3, 2, 0]  # whole history, as before


def test_period_days_are_costa_rica_days(db, accounts):
    # 14/10 at 23:00 in Costa Rica is 15/10 05:00 UTC: outside. 15/12 at 23:00 CR (16/12 05:00 UTC): inside.
    opp(db, accounts["Antes"], created=datetime(2026, 10, 15, 5))
    opp(db, accounts["Borde"], created=datetime(2026, 12, 16, 5))
    opp(db, accounts["Dentro"], created=datetime(2026, 12, 16, 6, 30))
    assert reached(funnel(db, period=PILOT))[0] == 1
    assert funnel(db, period=FunnelPeriod("x", date(2026, 10, 14), date(2026, 10, 14)))[0]["reached"] == 1


def test_default_period_is_the_pilot(db):
    period = funnel_period(db)
    assert (period.name, period.start, period.end) == ("Piloto", date(2026, 10, 15), date(2026, 12, 15))
    assert period.label == "Piloto (15/10/2026 – 15/12/2026)"


def post(client, url, data):
    return client.post(url, data=data, follow_redirects=False)


GOALS = {"prospecto": "150", "respuesta": "60", "reunion": "25", "propuesta": "10", "ganado": "4"}


def test_admin_edits_the_period(db, login_as, users):
    response = post(login_as("admin"), "/clientes/metas",
                    {**GOALS, "period_name": "Piloto 2", "period_start": "2026-11-01", "period_end": "2027-01-31"})
    assert response.status_code == 303
    period = funnel_period(db)
    assert (period.name, period.start, period.end) == ("Piloto 2", date(2026, 11, 1), date(2027, 1, 31))
    page = login_as("admin").get("/clientes").text
    assert "Piloto 2 (01/11/2026 – 31/01/2027)" in page
    assert "Todo el historial" in login_as("admin").get("/clientes?periodo=todo").text


def test_period_end_before_start_is_rejected(db, login_as, users):
    post(login_as("admin"), "/clientes/metas", {**GOALS, "period_start": "2026-12-01", "period_end": "2026-11-01"})
    db.expire_all()
    assert db.get(CrmSetting, "funnel_start") is None


def test_ventas_cannot_edit_the_period(db, login_as, users):
    response = post(login_as("ventas"), "/clientes/metas", {**GOALS, "period_start": "2026-11-01",
                                                             "period_end": "2026-11-30"})
    assert response.status_code in (302, 303, 403)
    assert db.get(CrmSetting, "funnel_start") is None


def test_dashboard_shows_the_period(login_as, users):
    assert "Piloto (15/10/2026 – 15/12/2026)" in login_as("admin").get("/dashboard").text


# --- Admin assigns opportunities -------------------------------------------------------

@pytest.fixture
def mails(monkeypatch):
    sent = []

    async def fake_send(recipients, subject, body):
        sent.append({"to": recipients, "subject": subject, "body": body})
    monkeypatch.setattr(crm_router, "send_plain_email", fake_send)
    return sent


def test_admin_assigns_an_opportunity_and_the_seller_gets_an_email(db, login_as, users, accounts, mails):
    melina = make_user(db, "melina", "ventas", full_name="Melina Rojas", email="melina@example.com")
    o = opp(db, accounts["Dentro"], next_step="Responder la solicitud", next_step_date=date(2026, 10, 20))
    form = {"title": o.title, "owner_id": str(melina.id), "next_step": "Responder la solicitud",
            "next_step_date": "2026-10-20"}
    response = post(login_as("admin"), f"/clientes/oportunidades/{o.id}/editar", form)
    assert response.status_code == 303
    db.expire_all()
    assert db.get(Opportunity, o.id).owner_id == melina.id
    assert mails == [{"to": ["melina@example.com"], "subject": "Oportunidad asignada: Dentro",
                      "body": mails[0]["body"]}]
    assert f"/clientes/oportunidades/{o.id}" in mails[0]["body"] and "Responder la solicitud" in mails[0]["body"]
    assert db.query(ActivityLog).filter(ActivityLog.details.like("%asignada a Melina Rojas%")).count() == 1
    # Saving again without changing the seller sends nothing.
    post(login_as("admin"), f"/clientes/oportunidades/{o.id}/editar", form)
    assert len(mails) == 1


def test_only_sellers_can_be_assigned(db, login_as, users, accounts, mails):
    o = opp(db, accounts["Dentro"])
    post(login_as("admin"), f"/clientes/oportunidades/{o.id}/editar",
         {"title": o.title, "owner_id": str(users["worker"].id)})
    db.expire_all()
    assert db.get(Opportunity, o.id).owner_id is None and not mails


# --- Guide ---------------------------------------------------------------------------

@pytest.mark.parametrize("role,status", [("admin", 200), ("ventas", 200), ("worker", 403), ("client", 403)])
def test_guide_access(role, status, login_as):
    response = login_as(role).get("/clientes/ayuda", follow_redirects=False)
    assert response.status_code == status or (status == 403 and response.status_code in (302, 303))
    if status == 200:
        assert "Cómo trabajar un prospecto" in response.text and "Piloto (15/10/2026 – 15/12/2026)" in response.text
