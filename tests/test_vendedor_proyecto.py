"""The project's vendedor encargado: sold it, oversees it administratively, earns its commissions
and sees its days in the calendar (docs/PLAN_PLANILLA_CALENDARIO.md)."""
from datetime import date

from app.db.models.commission import Commission
from app.db.models.project import Project
from app.db.models.schedule import ProjectSchedule
from tests.conftest import make_user
from tests.test_comisiones import commissions, pay, sale  # noqa: F401  (sale is a fixture)

DAY = date(2026, 11, 20)
RANGE = "/calendar/events?start=2026-11-01&end=2026-11-30"


def schedule(db, users, project_id=None):
    db.add(ProjectSchedule(project_id=project_id or users["project_id"], user_id=users["worker"].id, date=DAY))
    db.commit()


def other_seller(db):
    return make_user(db, "u_ventas2", "ventas")


def test_by_default_it_is_the_opportunity_owner(db, users, login_as, sale):
    schedule(db, users)
    event = login_as("admin").get(RANGE).json()[0]
    assert event["extendedProps"]["seller"]["id"] == sale["seller"].id
    assert event["extendedProps"]["seller_chosen"] is False


def test_admin_chooses_the_seller_from_the_calendar_and_back_to_default(db, users, login_as, sale):
    melina = other_seller(db)
    client = login_as("admin")
    response = client.post(f"/calendar/project/{users['project_id']}/seller", data={"seller_id": str(melina.id)})
    assert response.status_code == 200 and response.json()["seller"]["id"] == melina.id
    db.expire_all()
    assert db.get(Project, users["project_id"]).seller_id == melina.id
    response = client.post(f"/calendar/project/{users['project_id']}/seller", data={"seller_id": ""})
    assert response.json()["seller"]["id"] == sale["seller"].id and response.json()["seller_chosen"] is False


def test_only_people_who_sell_and_only_the_admin(db, users, login_as):
    path = f"/calendar/project/{users['project_id']}/seller"
    assert login_as("admin").post(path, data={"seller_id": str(users["worker"].id)}).status_code == 400
    assert login_as("supervisor").post(path, data={"seller_id": str(users["ventas"].id)}).status_code == 403
    assert login_as("ventas").post(path, data={"seller_id": str(users["ventas"].id)}).status_code == 403


def test_the_chosen_seller_earns_the_commission(db, users, login_as, sale):
    melina = other_seller(db)
    db.get(Project, users["project_id"]).seller_id = melina.id
    db.commit()
    pay(login_as("admin"), sale["invoices"][0])
    assert commissions(db)["factura"].user_id == melina.id


def test_a_seller_sees_only_the_days_of_their_projects(db, users, login_as, sale):
    schedule(db, users)
    other = Project(name="Otro proyecto", is_active=True)
    db.add(other)
    db.commit()
    schedule(db, users, other.id)
    client = login_as("ventas")
    assert client.get("/calendar/").status_code == 200
    events = client.get(RANGE).json()
    assert [e["extendedProps"]["project_name"] for e in events] == ["Proyecto de prueba"]
    assert events[0]["extendedProps"]["members"][0]["worker_name"]
    # Read only: no schedule changes.
    assert client.post("/calendar/schedule", data={}).status_code in (403, 422)


def test_a_seller_with_no_projects_sees_an_empty_calendar(db, users, login_as):
    schedule(db, users)
    assert login_as("ventas").get(RANGE).json() == []


def test_project_form_saves_the_seller(db, users, login_as, sale):
    client = login_as("admin")
    page = client.get(f"/projects/{users['project_id']}/edit").text
    assert "Vendedor encargado" in page and "Según la oportunidad o la cuenta" in page
    melina = other_seller(db)
    line = sale["invoices"][0].line
    body = {"name": "Proyecto de prueba", "account_id": sale["account"].id, "seller_id": melina.id,
            "budget_lines": [{"id": line.id, "name": line.name, "subtotal": line.subtotal,
                              "tax_percentage": line.tax_percentage}]}
    response = client.post(f"/projects/{users['project_id']}/edit", json=body)
    assert response.status_code == 200, response.text
    db.expire_all()
    assert db.get(Project, users["project_id"]).seller_id == melina.id
    body["seller_id"] = users["worker"].id
    assert client.post(f"/projects/{users['project_id']}/edit", json=body).status_code == 400
    body["seller_id"] = None
    assert client.post(f"/projects/{users['project_id']}/edit", json=body).status_code == 200
    db.expire_all()
    assert db.get(Project, users["project_id"]).seller_id is None


def test_project_page_shows_the_seller_but_not_to_the_client(db, users, login_as, sale):
    path = f"/projects/{users['project_id']}"
    assert "Vendedor encargado" in login_as("admin").get(path).text
    assert "Vendedor encargado" not in login_as("client").get(path).text
