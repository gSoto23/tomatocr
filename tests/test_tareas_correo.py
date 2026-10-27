"""E-mail for Dashboard tasks: to who is assigned a task by someone else, and to the people of
a task when it becomes "alta". Never to who made the change, nor to someone without an e-mail."""
import pytest

from app.db.models.task import Task
from app.routers import dashboard as dashboard_router
from tests.test_dashboard_tareas import TODAY, add_task


@pytest.fixture
def mails(monkeypatch, db, users):
    for role in ("admin", "supervisor", "worker", "ventas"):
        users[role].email = f"{role}@example.com"
    db.commit()
    sent = []

    async def fake_send(recipients, subject, body):
        sent.append({"to": recipients, "subject": subject, "body": body})
    monkeypatch.setattr(dashboard_router, "send_plain_email", fake_send)
    return sent


def edit(client, task, people, priority="normal", **fields):
    data = {"title": task.title, "due_date": task.due_date.isoformat(), "priority": priority,
            "assignees_sent": "1", "assignee_ids": [str(i) for i in people]}
    data.update(fields)
    return client.post(f"/dashboard/tareas/{task.id}/editar", data=data)


def test_assigning_a_task_mails_each_person(db, login_as, users, mails):
    add_task(login_as("supervisor"), [users["worker"].id, users["ventas"].id], title="Podar el parque",
             description="Llevar la escalera")
    assert sorted(m["to"][0] for m in mails) == ["ventas@example.com", "worker@example.com"]
    mail = next(m for m in mails if m["to"] == ["worker@example.com"])
    assert mail["subject"] == "Tarea asignada: Podar el parque"
    assert "u_supervisor te asignó una tarea." in mail["body"] and "Llevar la escalera" in mail["body"]
    assert f"Vence: {TODAY:%d/%m/%Y}" in mail["body"] and "Junto con: u_ventas" in mail["body"]
    assert "https://tomatocr.com/dashboard/" in mail["body"]


def test_a_task_for_yourself_sends_nothing(db, login_as, users, mails):
    add_task(login_as("worker"), priority="alta")
    add_task(login_as("supervisor"), [users["supervisor"].id], priority="alta")
    assert mails == []


def test_who_assigns_is_not_mailed(db, login_as, users, mails):
    add_task(login_as("supervisor"), [users["supervisor"].id, users["worker"].id])
    assert [m["to"] for m in mails] == [["worker@example.com"]]


def test_a_high_priority_assignment_says_so(db, login_as, users, mails):
    add_task(login_as("admin"), [users["worker"].id], title="Revisar riego", priority="alta")
    assert mails[0]["subject"] == "[Alta] Tarea asignada: Revisar riego"
    assert "Prioridad: Alta" in mails[0]["body"]


def test_someone_without_email_is_skipped(db, login_as, users, mails):
    users["ventas"].email = None
    db.commit()
    add_task(login_as("supervisor"), [users["worker"].id, users["ventas"].id])
    assert [m["to"] for m in mails] == [["worker@example.com"]]


def test_editing_mails_only_who_was_added(db, login_as, users, mails):
    client = login_as("supervisor")
    add_task(client, [users["worker"].id])
    task = db.query(Task).one()
    mails.clear()
    edit(client, task, [users["worker"].id, users["ventas"].id], title="Llamar al vivero hoy")
    assert [(m["to"], m["subject"]) for m in mails] == [(["ventas@example.com"], "Tarea asignada: Llamar al vivero hoy")]
    mails.clear()
    edit(client, task, [users["worker"].id, users["ventas"].id], title="Otro título")
    assert mails == []


def test_raising_to_alta_mails_who_still_has_to_do_it(db, login_as, users, mails):
    client = login_as("supervisor")
    add_task(client, [users["worker"].id, users["ventas"].id, users["admin"].id])
    task = db.query(Task).one()
    login_as("admin").post(f"/dashboard/tareas/{task.id}/hecha")
    mails.clear()
    edit(client, task, [users["worker"].id, users["ventas"].id, users["admin"].id], priority="alta")
    assert sorted(m["to"][0] for m in mails) == ["ventas@example.com", "worker@example.com"]  # admin already did it
    assert all(m["subject"] == "Tarea en prioridad alta: Llamar al vivero" for m in mails)
    assert "u_supervisor pasó a prioridad alta una tarea tuya." in mails[0]["body"]
    mails.clear()
    edit(client, task, [users["worker"].id, users["ventas"].id, users["admin"].id], priority="alta")
    assert mails == []  # it was already alta


def test_raising_your_own_task_sends_nothing(db, login_as, users, mails):
    client = login_as("worker")
    add_task(client)
    task = db.query(Task).one()
    client.post(f"/dashboard/tareas/{task.id}/editar",
                data={"title": task.title, "due_date": task.due_date.isoformat(), "priority": "alta"})
    db.expire_all()
    assert db.get(Task, task.id).priority == "alta" and mails == []
