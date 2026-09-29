"""Money goals (tenders vs one-off jobs), proposal coverage, the opportunity's origin, and
discarded accounts kept out of the next steps."""
from datetime import date, datetime, timedelta

import pytest

from app.db.models.crm import Account, CrmGoal, Opportunity, stage_index
from app.db.models.finance import BudgetLine, ProjectBudget
from app.db.models.project import Project
from app.utils.crm import change_stage, funnel_period, money_progress, next_steps, set_funnel_period
from tests.test_crm_entradas import FORM, mails, post_form, sellers  # noqa: F401 (fixtures)

TODAY = date.today()


@pytest.fixture
def period(db):
    set_funnel_period(db, "Prueba", TODAY - timedelta(days=10), TODAY + timedelta(days=10))
    return funnel_period(db)


def opportunity(db, name, motor, stage="propuesta", amount=None, **extra):
    account = Account(name=name)
    db.add(account)
    db.flush()
    opp = Opportunity(account_id=account.id, title=name, motor=motor, stage=stage, max_stage=stage_index(stage),
                      amount_crc=amount, **extra)
    db.add(opp)
    db.flush()
    return opp


def test_money_goals_split_tenders_and_one_off_jobs(db, users, period):
    project = db.get(Project, users["project_id"])
    tender = opportunity(db, "Municipalidad", "sector_publico", stage="reunion", amount=1)
    budget = ProjectBudget(project_id=project.id)
    db.add(budget)
    db.flush()
    db.add(BudgetLine(budget_id=budget.id, name="Mantenimiento", subtotal=10_000_000, tax_percentage=13))
    tender.project_id = project.id
    change_stage(db, tender, "ganado", users["admin"])
    assert tender.won_at is not None
    job = opportunity(db, "Casa", "mantenimiento", stage="ganado", amount=300_000, won_at=datetime.utcnow())
    opportunity(db, "Vieja", "mantenimiento", stage="ganado", amount=999, won_at=datetime.utcnow() - timedelta(days=60))
    opportunity(db, "Propuesta chica", "mantenimiento", amount=2_100_000)
    opportunity(db, "Licitación abierta", "sector_publico", amount=40_000_000)
    db.add_all([CrmGoal(stage="monto_licitaciones", target=15_000_000), CrmGoal(stage="monto_puntuales", target=1_000_000)])
    db.commit()
    rows = {r["key"]: r for r in money_progress(db, period)}
    tenders, jobs = rows["monto_licitaciones"], rows["monto_puntuales"]
    assert round(tenders["won"]) == 11_300_000 and tenders["count"] == 1  # adjudicated in Presupuestos, with tax
    assert round(tenders["missing"]) == 3_700_000 and tenders["coverage"] == round(40_000_000 / 3_700_000, 1)
    assert jobs["won"] == job.amount_crc and jobs["count"] == 1  # the one won 60 days ago doesn't count
    assert jobs["coverage"] == 3.0 and jobs["pct"] == 30


def test_leaving_ganado_clears_the_date(db, users):
    opp = opportunity(db, "Casa", "mantenimiento", stage="ganado", won_at=datetime.utcnow())
    change_stage(db, opp, "propuesta", users["admin"])
    assert opp.won_at is None


def test_admin_sets_money_goals_and_sees_them(db, login_as, period):
    admin = login_as("admin")
    admin.post("/clientes/metas", data={"propuesta": "10", "ganado": "4", "monto_licitaciones": "15,000,000",
                                        "monto_puntuales": "₡2.000.000"})
    assert db.get(CrmGoal, "monto_licitaciones").target == 15_000_000
    assert db.get(CrmGoal, "monto_puntuales").target == 2_000_000
    html = admin.get("/clientes").text
    assert "Licitaciones" in html and "Trabajos puntuales" in html and "₡15,000,000" in html
    assert "Ganado en el periodo" in admin.get("/dashboard/").text
    assert login_as("ventas").post("/clientes/metas", data={"monto_puntuales": "1"},
                                   follow_redirects=False).status_code == 403


def test_origin_is_set_edited_and_filtered(db, login_as, users, sellers, mails):  # noqa: F811
    post_form(FORM)
    assert db.query(Opportunity).one().origin == "web"
    account = Account(name="Referida SA", owner_id=users["ventas"].id)
    db.add(account)
    db.commit()
    ventas = login_as("ventas")
    ventas.post(f"/clientes/cuentas/{account.id}/oportunidades", data={"title": "Jardín", "origin": "referido"})
    referred = db.query(Opportunity).filter(Opportunity.account_id == account.id).one()
    assert referred.origin == "referido"
    ventas.post(f"/clientes/oportunidades/{referred.id}/editar", data={"title": "Jardín", "origin": "prospeccion"})
    db.expire_all()
    assert db.get(Opportunity, referred.id).origin == "prospeccion"
    html = ventas.get("/clientes?origen=web").text
    assert "Hotel Bosque" in html and "Referida SA" not in html
    assert "Referida SA" in ventas.get("/clientes?origen=prospeccion").text


def test_discarded_accounts_leave_the_next_steps(db, users):
    opp = opportunity(db, "Descartada vieja", "tienda", stage="prospecto", next_step="Responder",
                      next_step_date=TODAY)
    db.commit()
    assert [o.id for o in next_steps(db)["hoy"]] == [opp.id]
    opp.account.discarded_at = datetime.utcnow()  # discarded with the old button: the opportunity stayed open
    db.commit()
    assert next_steps(db)["hoy"] == []
