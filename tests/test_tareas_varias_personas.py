"""A Dashboard task for several people: admin and supervisor pick them, each one marks their
own part done, and who assigned it sees who already did it."""
from datetime import timedelta

import pytest

from app.db.models.task import Task, TaskAssignee
from tests.test_dashboard_tareas import TODAY, add_task, people_of


@pytest.fixture
def shared(db, login_as, users):
    add_task(login_as("supervisor"), [users["worker"].id, users["ventas"].id], title="Entregar el reporte")
    return db.query(Task).one()


def test_one_task_for_several_people(db, login_as, users, shared):
    assert people_of(shared) == [users["worker"].id, users["ventas"].id]
    for role, other in (("worker", "ventas"), ("ventas", "worker")):
        hoy = login_as(role).get("/dashboard/").text
        assert "Entregar el reporte" in hoy and "te la asignó" in hoy and "0 de 2 hechas" in hoy
        assert (users[other].full_name or users[other].username) in hoy


def test_each_one_marks_their_part(db, login_as, users, shared):
    login_as("worker").post(f"/dashboard/tareas/{shared.id}/hecha")
    db.expire_all()
    done = {a.user_id: a.done_at for a in db.get(Task, shared.id).assignees}
    assert done[users["worker"].id] and done[users["ventas"].id] is None
    assert "Hechas hoy (1)" in login_as("worker").get("/dashboard/").text
    ventas = login_as("ventas").get("/dashboard/").text
    assert "1 de 2 hecha" in ventas and "Hechas hoy" not in ventas
    supervisor = login_as("supervisor").get("/dashboard/").text
    assert "Que asigné a otros (1)" in supervisor and "1 de 2 hecha" in supervisor

    login_as("ventas").post(f"/dashboard/tareas/{shared.id}/hecha")
    assert "Que asigné a otros" not in login_as("supervisor").get("/dashboard/").text  # everybody did it


def test_only_the_people_of_the_task_mark_it(db, login_as, shared):
    assert login_as("supervisor").post(f"/dashboard/tareas/{shared.id}/hecha").status_code == 403
    assert login_as("admin").post(f"/dashboard/tareas/{shared.id}/hecha").status_code == 403


def test_a_shared_task_is_changed_only_by_who_assigned_it(db, login_as, users, shared):
    form = {"title": "Otro", "due_date": TODAY.isoformat(), "priority": "normal"}
    assert login_as("worker").post(f"/dashboard/tareas/{shared.id}/editar", data=form).status_code == 403
    assert login_as("worker").post(f"/dashboard/tareas/{shared.id}/borrar").status_code == 403
    assert "Borrar tarea (para todos)" not in login_as("worker").get("/dashboard/").text
    assert "Borrar tarea (para todos)" in login_as("supervisor").get("/dashboard/").text


def test_editing_who_keeps_the_done_marks(db, login_as, users, shared):
    login_as("worker").post(f"/dashboard/tareas/{shared.id}/hecha")
    login_as("supervisor").post(f"/dashboard/tareas/{shared.id}/editar", data={
        "title": "Entregar el reporte", "due_date": TODAY.isoformat(), "priority": "alta", "assignees_sent": "1",
        "assignee_ids": [str(users["worker"].id), str(users["admin"].id)]})
    db.expire_all()
    task = db.get(Task, shared.id)
    assert people_of(task) == [users["worker"].id, users["admin"].id] and task.priority == "alta"
    assert task.part_of(users["worker"].id).done_at is not None
    assert "Entregar el reporte" not in login_as("ventas").get("/dashboard/").text


def test_at_least_one_person(db, login_as, users, shared):
    add_task(login_as("supervisor"), [], title="Sin nadie")
    assert db.query(Task).filter_by(title="Sin nadie").count() == 0
    login_as("supervisor").post(f"/dashboard/tareas/{shared.id}/editar", data={
        "title": "X", "due_date": TODAY.isoformat(), "assignees_sent": "1"})
    db.expire_all()
    assert db.get(Task, shared.id).title == "Entregar el reporte"


def test_editing_without_para_keeps_the_people(db, login_as, users):
    add_task(login_as("supervisor"), [users["worker"].id], title="Solo una")
    task = db.query(Task).one()
    login_as("worker").post(f"/dashboard/tareas/{task.id}/editar", data={
        "title": "Solo una, cambiada", "due_date": (TODAY + timedelta(days=1)).isoformat()})
    db.expire_all()
    task = db.get(Task, task.id)
    assert task.title == "Solo una, cambiada" and people_of(task) == [users["worker"].id]


def test_the_assigner_can_be_one_of_them(db, login_as, users):
    add_task(login_as("admin"), [users["admin"].id, users["supervisor"].id], title="Reunión de equipo")
    html = login_as("admin").get("/dashboard/").text
    assert "Reunión de equipo" in html and "Que asigné a otros" not in html  # in Mis tareas, not twice


def test_deleting_removes_everybody_part(db, login_as, shared):
    login_as("supervisor").post(f"/dashboard/tareas/{shared.id}/borrar")
    assert db.query(Task).count() == 0 and db.query(TaskAssignee).count() == 0


def test_the_form_has_the_people_boxes(login_as):
    html = login_as("supervisor").get("/dashboard/").text
    assert 'name="assignee_ids"' in html and 'name="assignees_sent"' in html and "podés marcar varias personas" in html
