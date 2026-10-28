"""Notifications: the bell, the e-mail outbox (retries, quiet hours, two processes), what each
person wants by e-mail, the daily digest and the run of scripts/notificaciones.py."""
import asyncio
import re
from datetime import datetime, time, timedelta

import pytest

from app.db.models.notification import DigestSent, Notification, NotificationPref
from app.db.models.task import Task
from app.utils import notifications
from app.utils.notifications import MAX_ATTEMPTS, deliver, notify, run_once, send_digests
from tests.conftest import NOON_CR
from tests.test_dashboard_tareas import TODAY, add_task


@pytest.fixture
def team(db, users):
    for role in ("admin", "supervisor", "worker", "ventas"):
        users[role].email = f"{role}@example.com"
    db.commit()
    return users


def run(coro):
    return asyncio.run(coro)


def at(monkeypatch, hour, minute=0):
    moment = datetime.combine(NOON_CR.date(), time(hour, minute))
    monkeypatch.setattr(notifications, "now_cr", lambda: moment)
    return moment


# --- The bell ---------------------------------------------------------------------

def test_an_assigned_task_shows_in_the_bell(db, login_as, team, outbox):
    add_task(login_as("supervisor"), [team["worker"].id], title="Regar el vivero")
    worker = login_as("worker")
    assert 'aria-label="Notificaciones: 1 sin leer"' in worker.get("/dashboard/").text
    page = worker.get("/notificaciones").text
    assert "Tarea asignada: Regar el vivero" in page and "1 sin leer" in page and "enviada por correo" in page
    assert 'aria-label="Notificaciones"' in login_as("supervisor").get("/dashboard/").text  # nothing for who assigned


def test_opening_one_marks_it_read_and_goes_to_its_page(db, login_as, team):
    add_task(login_as("supervisor"), [team["worker"].id])
    notice = db.query(Notification).one()
    worker = login_as("worker")
    response = worker.post(f"/notificaciones/{notice.id}/abrir", follow_redirects=False)
    assert response.status_code == 303 and response.headers["location"] == "/dashboard/"
    db.expire_all()
    assert db.get(Notification, notice.id).read_at is not None
    assert 'aria-label="Notificaciones"' in worker.get("/dashboard/").text


def test_nobody_opens_someone_elses(db, login_as, team):
    add_task(login_as("supervisor"), [team["worker"].id])
    notice = db.query(Notification).one()
    assert login_as("ventas").post(f"/notificaciones/{notice.id}/abrir").status_code == 404
    db.expire_all()
    assert db.get(Notification, notice.id).read_at is None


def test_mark_all_read(db, login_as, team):
    supervisor = login_as("supervisor")
    add_task(supervisor, [team["worker"].id], title="Uno")
    add_task(supervisor, [team["worker"].id], title="Dos")
    login_as("worker").post("/notificaciones/leidas")
    assert db.query(Notification).filter(Notification.read_at.is_(None)).count() == 0


def test_the_client_has_no_bell(db, login_as, team):
    client = login_as("client")
    assert "data-bell" not in client.get("/dashboard/").text
    assert client.get("/notificaciones").status_code == 403


def test_the_last_one_to_finish_tells_who_assigned_it(db, login_as, team, outbox):
    add_task(login_as("supervisor"), [team["worker"].id, team["ventas"].id], title="Inventario")
    task = db.query(Task).one()
    outbox.clear()
    login_as("worker").post(f"/dashboard/tareas/{task.id}/hecha")
    assert db.query(Notification).filter_by(kind="task_done").count() == 0
    login_as("ventas").post(f"/dashboard/tareas/{task.id}/hecha")
    done = db.query(Notification).filter_by(kind="task_done").one()
    assert done.user_id == team["supervisor"].id and done.title == "Tarea terminada: Inventario"
    assert "u_worker, u_ventas" in done.body
    assert done.email_status == "none" and outbox == []  # only the bell, unless they ask for it


# --- Preferences ------------------------------------------------------------------

def test_turning_off_an_email_keeps_the_bell(db, login_as, team, outbox):
    worker = login_as("worker")
    page = worker.get("/notificaciones").text
    assert 'name="email_task_assigned" value="1" checked' in page
    assert not re.search(r'name="email_task_done" value="1"\s+checked', page)  # off by default
    worker.post("/notificaciones/preferencias", data={"email_task_high": "1", "email_daily_digest": "1"})
    assert db.query(NotificationPref).filter_by(user_id=team["worker"].id, kind="task_assigned").one().email is False
    add_task(login_as("supervisor"), [team["worker"].id])
    notice = db.query(Notification).one()
    assert notice.email_status == "none" and outbox == []


def test_turning_on_task_done_emails_it(db, login_as, team, outbox):
    login_as("supervisor").post("/notificaciones/preferencias",
                                data={"email_task_assigned": "1", "email_task_done": "1"})
    add_task(login_as("supervisor"), [team["worker"].id], title="Podar")
    task = db.query(Task).one()
    login_as("worker").post(f"/dashboard/tareas/{task.id}/hecha")
    assert [m["subject"] for m in outbox if m["to"] == ["supervisor@example.com"]] == ["Tarea terminada: Podar"]


def test_without_email_it_says_so(db, login_as, users):
    page = login_as("worker").get("/notificaciones").text
    assert "Tu usuario no tiene correo" in page


# --- The outbox -------------------------------------------------------------------

def test_the_email_has_the_link_and_how_to_change_it(db, login_as, team, outbox):
    add_task(login_as("supervisor"), [team["worker"].id])
    body = outbox[0]["body"]
    assert "Ver en el sistema: https://tomatocr.com/dashboard/" in body
    assert "https://tomatocr.com/notificaciones" in body


def test_at_night_only_urgent_ones_go_and_the_rest_wait_for_the_morning(db, login_as, team, outbox, monkeypatch):
    at(monkeypatch, 22)
    supervisor = login_as("supervisor")
    add_task(supervisor, [team["worker"].id], title="Normal")
    add_task(supervisor, [team["ventas"].id], title="Urgente", priority="alta")
    assert [m["subject"] for m in outbox] == ["[Alta] Tarea asignada: Urgente"]
    assert db.query(Notification).filter_by(email_status="pending").count() == 1
    at(monkeypatch, 6, 5)
    run(run_once())
    assert [m["subject"] for m in outbox][-1] == "Tarea asignada: Normal"
    assert db.query(Notification).filter_by(email_status="pending").count() == 0


def test_a_failure_is_retried_and_then_given_up(db, team, monkeypatch, outbox):
    notice = notify(db, team["worker"], "task_assigned", "Prueba", "Cuerpo", "/dashboard/")
    db.commit()

    async def down(*args):
        return False
    monkeypatch.setattr(notifications, "send_plain_email", down)
    for attempt in range(1, MAX_ATTEMPTS + 1):
        run(deliver())
        db.expire_all()
        assert db.get(Notification, notice.id).email_attempts == attempt
    assert db.get(Notification, notice.id).email_status == "failed"
    run(deliver())
    db.expire_all()
    assert db.get(Notification, notice.id).email_attempts == MAX_ATTEMPTS


def test_a_retry_that_works_sends_it_once(db, team, monkeypatch, outbox):
    notice = notify(db, team["worker"], "task_assigned", "Prueba")
    db.commit()
    calls = []

    async def flaky(recipients, subject, body):
        calls.append(subject)
        return len(calls) > 1
    monkeypatch.setattr(notifications, "send_plain_email", flaky)
    run(deliver())
    run(deliver())
    run(deliver())
    db.expire_all()
    assert calls == ["Prueba", "Prueba"] and db.get(Notification, notice.id).email_status == "sent"


def test_one_taken_by_another_process_is_not_sent_again(db, team, outbox):
    notice = notify(db, team["worker"], "task_assigned", "Prueba")
    db.commit()
    notice.email_status = "sending"
    notice.emailed_at = datetime.utcnow()
    db.commit()
    run(run_once())
    assert outbox == []
    notice.emailed_at = datetime.utcnow() - timedelta(minutes=20)  # that process died
    db.commit()
    run(run_once())
    assert [m["subject"] for m in outbox] == ["Prueba"]


def test_someone_who_lost_their_email_is_skipped(db, team, outbox):
    notice = notify(db, team["worker"], "task_assigned", "Prueba")
    db.commit()
    team["worker"].email = None
    db.commit()
    run(deliver())
    db.expire_all()
    assert db.get(Notification, notice.id).email_status == "none" and outbox == []


def test_old_read_ones_are_deleted(db, team):
    old = notify(db, team["worker"], "task_assigned", "Vieja")
    unread = notify(db, team["worker"], "task_assigned", "Sin leer")
    db.commit()
    old.read_at = datetime.utcnow() - timedelta(days=100)
    unread.created_at = datetime.utcnow() - timedelta(days=100)
    db.commit()
    run(run_once())
    assert [n.title for n in db.query(Notification)] == ["Sin leer"]


# --- Daily digest -----------------------------------------------------------------

def test_the_digest_goes_once_in_the_morning_to_who_has_something(db, login_as, team, outbox, monkeypatch):
    add_task(login_as("worker"), title="Llenar la bitácora", priority="alta")
    add_task(login_as("ventas"), title="Para mañana", due_date=(TODAY + timedelta(days=1)).isoformat())
    outbox.clear()
    at(monkeypatch, 6, 30)
    run(run_once())
    assert outbox == []  # too early
    moment = at(monkeypatch, 7, 0)
    run(send_digests(db, moment.replace(year=TODAY.year, month=TODAY.month, day=TODAY.day)))
    worker = [m for m in outbox if m["to"] == ["worker@example.com"]]
    assert len(worker) == 1 and worker[0]["subject"].startswith("Tu día en TOMATO: 1 tarea")
    assert "- Llenar la bitácora [Alta]" in worker[0]["body"]
    assert not [m for m in outbox if m["to"] == ["ventas@example.com"]]  # nothing for today
    assert db.query(DigestSent).filter_by(day=TODAY).count() >= 2  # also those with nothing, so it isn't recomputed
    outbox.clear()
    run(send_digests(db, moment.replace(year=TODAY.year, month=TODAY.month, day=TODAY.day, hour=9)))
    assert not [m for m in outbox if m["to"] == ["worker@example.com"]]


def test_the_digest_can_be_turned_off(db, login_as, team, outbox, monkeypatch):
    worker = login_as("worker")
    add_task(worker, title="Algo")
    worker.post("/notificaciones/preferencias", data={"email_task_assigned": "1"})
    moment = datetime.combine(TODAY, time(7, 30))
    run(send_digests(db, moment))
    assert not [m for m in outbox if m["to"] == ["worker@example.com"]]


def test_no_digest_after_noon_or_for_the_client(db, login_as, team, outbox):
    add_task(login_as("worker"), title="Algo")
    run(send_digests(db, datetime.combine(TODAY, time(12, 30))))
    assert outbox == []
    team["client"].email = "client@example.com"
    db.commit()
    run(send_digests(db, datetime.combine(TODAY, time(7, 30))))
    assert not [m for m in outbox if m["to"] == ["client@example.com"]]


# --- Other notices ----------------------------------------------------------------

def test_the_script_runs(db, team, outbox):
    notify(db, team["worker"], "task_assigned", "Desde el script")
    db.commit()
    from scripts import notificaciones as script  # noqa: F401
    assert run(run_once())["sent"] == 1


def test_the_digest_is_also_in_the_bell(db, login_as, team, outbox):
    add_task(login_as("worker"), title="Llenar la bitácora")
    run(send_digests(db, datetime.combine(TODAY, time(7, 0))))
    notice = db.query(Notification).filter_by(kind="daily_digest", user_id=team["worker"].id).one()
    assert notice.title.startswith("Tu día en TOMATO: 1 tarea") and "- Llenar la bitácora" in notice.body
    assert notice.link == "/dashboard/" and notice.email_status == "none"  # the e-mail went on its own
    assert "Ver en el sistema" not in notice.body
    assert 'aria-label="Notificaciones: 1 sin leer"' in login_as("worker").get("/dashboard/").text


def test_without_email_or_with_it_off_the_digest_still_reaches_the_bell(db, login_as, users, outbox):
    worker = login_as("worker")  # no e-mail
    add_task(worker, title="Algo")
    run(send_digests(db, datetime.combine(TODAY, time(7, 0))))
    assert db.query(Notification).filter_by(kind="daily_digest").count() == 1 and outbox == []


def test_one_failing_digest_does_not_stop_the_rest(db, login_as, team, outbox, monkeypatch):
    add_task(login_as("worker"), title="Algo")
    add_task(login_as("ventas"), title="Otra cosa")
    real = notifications.digest

    def broken_for_worker(db, user, today):
        if user.id == team["worker"].id:
            raise RuntimeError("datos raros")
        return real(db, user, today)
    monkeypatch.setattr(notifications, "digest", broken_for_worker)
    run(send_digests(db, datetime.combine(TODAY, time(7, 0))))
    assert [m["to"] for m in outbox] == [["ventas@example.com"]]
    assert db.query(DigestSent).filter_by(user_id=team["worker"].id).count() == 0  # retried next run
    monkeypatch.setattr(notifications, "digest", real)
    run(send_digests(db, datetime.combine(TODAY, time(7, 5))))
    assert [m["to"] for m in outbox][-1] == ["worker@example.com"]
