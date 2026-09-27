"""Editing a project that reports, calendar entries and invoices already use.
Used to delete and recreate tasks, sedes and budget lines, which PostgreSQL
rejects (foreign keys) and SQLite silently broke. app/utils/project_sync.py."""
from datetime import date

import pytest

from app.db.models.crm import Account
from app.db.models.finance import BudgetLine, Invoice, ProjectBudget
from app.db.models.log import DailyLog
from app.db.models.log_task import DailyLogTask
from app.db.models.project import Project
from app.db.models.project_details import ProjectLocation, ProjectTask
from app.db.models.schedule import ProjectSchedule


@pytest.fixture
def busy(db, users):
    """A project with two tasks, two sedes and a budget line; a report uses task 1 at
    sede 1, a calendar entry uses sede 2, an invoice uses the line."""
    account = Account(name="Condominio Sol")
    db.add(account)
    db.flush()
    project = db.get(Project, users["project_id"])
    project.account_id = account.id
    t1 = ProjectTask(project_id=project.id, description="Cortar zacate", is_required=True)
    t2 = ProjectTask(project_id=project.id, description="Podar setos", is_required=False)
    s1 = ProjectLocation(project_id=project.id, name="Sede Norte")
    s2 = ProjectLocation(project_id=project.id, name="Sede Sur")
    budget = ProjectBudget(project_id=project.id)
    db.add_all([t1, t2, s1, s2, budget])
    db.flush()
    line = BudgetLine(budget_id=budget.id, name="Mantenimiento", subtotal=1000, tax_percentage=13)
    db.add(line)
    db.flush()
    log = DailyLog(project_id=project.id, user_id=users["worker"].id, date=date.today(), notes="Listo",
                   location_id=s1.id)
    db.add(log)
    db.flush()
    db.add_all([DailyLogTask(log_id=log.id, task_id=t1.id, completed=True),
                ProjectSchedule(project_id=project.id, user_id=users["worker"].id, date=date.today(),
                                location_id=s2.id),
                Invoice(budget_id=budget.id, budget_line_id=line.id, invoice_number="F-1", issue_date=date.today(),
                        due_date=date.today(), amount=500)])
    db.commit()
    return {"project": project, "account": account, "t1": t1, "t2": t2, "s1": s1, "s2": s2, "line": line, "log": log}


def payload(b, **changes):
    data = {
        "name": "Proyecto de prueba", "account_id": b["account"].id,
        "tasks": [{"id": b["t1"].id, "description": "Cortar zacate", "is_required": True},
                  {"id": b["t2"].id, "description": "Podar setos", "is_required": False}],
        "locations": [{"id": b["s1"].id, "name": "Sede Norte"}, {"id": b["s2"].id, "name": "Sede Sur"}],
        "budget_lines": [{"id": b["line"].id, "name": "Mantenimiento", "subtotal": 1000, "tax_percentage": 13}],
    }
    data.update(changes)
    return data


def save(client, b, data):
    return client.post(f"/projects/{b['project'].id}/edit", json=data)


def test_saving_unchanged_keeps_every_row(db, login_as, busy):
    assert save(login_as("admin"), busy, payload(busy)).status_code == 200
    db.expire_all()
    assert [t.id for t in db.get(Project, busy["project"].id).tasks] == [busy["t1"].id, busy["t2"].id]
    assert db.get(DailyLog, busy["log"].id).location_id == busy["s1"].id
    assert db.query(Invoice).one().budget_line_id == busy["line"].id


def test_renaming_keeps_the_same_row(db, login_as, busy):
    data = payload(busy)
    data["tasks"][0]["description"] = "Cortar césped"
    data["locations"][0]["name"] = "Sede Central"
    data["budget_lines"][0]["subtotal"] = 1500
    assert save(login_as("admin"), busy, data).status_code == 200
    db.expire_all()
    assert db.get(ProjectTask, busy["t1"].id).description == "Cortar césped"
    assert db.get(ProjectLocation, busy["s1"].id).name == "Sede Central"
    assert db.get(BudgetLine, busy["line"].id).subtotal == 1500


def test_removing_used_rows_archives_them_and_old_reports_keep_them(db, login_as, busy):
    client = login_as("admin")
    ids = {k: busy[k].id for k in ("t1", "t2", "s1", "s2")}
    data = payload(busy, tasks=[{"description": "Regar", "is_required": True}], locations=[])
    assert save(client, busy, data).status_code == 200
    db.expire_all()
    project = db.get(Project, busy["project"].id)
    assert [t.description for t in project.tasks] == ["Regar"]
    assert project.locations == []
    assert db.get(ProjectTask, ids["t1"]).archived_at is not None      # used by the report
    assert db.get(ProjectTask, ids["t2"]) is None                       # unused: deleted
    assert db.get(ProjectLocation, ids["s1"]).archived_at is not None  # used by the report
    assert db.get(ProjectLocation, ids["s2"]).archived_at is not None  # used by the calendar
    detail = client.get(f"/logs/{busy['log'].id}/detail").json()
    assert detail["location_name"] == "Sede Norte"
    assert {t["description"]: t["completed"] for t in detail["tasks"]} == {"Regar": False, "Cortar zacate": True}
    assert "Cortar zacate" not in client.get(f"/logs/new?project_id={project.id}").text


def test_line_with_invoices_cannot_be_removed(db, login_as, busy):
    response = save(login_as("admin"), busy, payload(busy, budget_lines=[], name="Otro nombre"))
    assert response.status_code == 400
    assert "tiene facturas" in response.json()["detail"]
    db.expire_all()
    assert db.get(Project, busy["project"].id).name == "Proyecto de prueba"  # nothing saved
    assert db.get(BudgetLine, busy["line"].id) is not None


def test_callers_without_ids_match_by_name(db, login_as, busy):
    data = payload(busy)
    for key in ("tasks", "locations", "budget_lines"):
        for item in data[key]:
            item.pop("id")
    assert save(login_as("admin"), busy, data).status_code == 200
    db.expire_all()
    assert [t.id for t in db.get(Project, busy["project"].id).tasks] == [busy["t1"].id, busy["t2"].id]


def test_editing_a_report_keeps_its_sede(db, login_as, busy):
    client = login_as("admin")
    response = client.post(f"/logs/{busy['log'].id}/edit", data={"notes": "Corregido", "tasks": [busy["t1"].id]},
                           follow_redirects=False)
    assert response.status_code == 303
    db.expire_all()
    log = db.get(DailyLog, busy["log"].id)
    assert (log.notes, log.location_id) == ("Corregido", busy["s1"].id)


def test_form_sends_the_ids(login_as, busy):
    html = login_as("admin").get(f"/projects/{busy['project'].id}/edit").text
    assert f"id: {busy['t1'].id}," in html and f"id: {busy['s1'].id}," in html and f"id: {busy['line'].id}," in html
