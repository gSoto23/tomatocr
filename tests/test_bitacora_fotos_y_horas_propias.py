"""Two reports from the field (22/11/2026): a supervisor who "can't approve" their own hours
(the rule: the admin confirms them; now shown, not hidden, and enforced on every endpoint),
and a Bitácora report that failed with "Error desconocido" (now the page says what failed)."""
from datetime import date
from pathlib import Path

import pytest

from app.db.models.log import DailyLog
from app.db.models.schedule import ProjectSchedule
from app.routers import logs as logs_router
from app.utils.timecr import today_cr

DAY = date(2026, 11, 20)


@pytest.fixture
def days(db, users):
    """One day of the project for the supervisor and one for the worker, not confirmed."""
    rows = {role: ProjectSchedule(project_id=users["project_id"], user_id=users[role].id, date=DAY,
                                  hours_worked=8, overtime_hours=0, is_confirmed=False)
            for role in ("supervisor", "worker")}
    db.add_all(rows.values())
    db.commit()
    return {role: row.id for role, row in rows.items()}


def confirmed(db, schedule_id):
    db.expire_all()
    return db.get(ProjectSchedule, schedule_id).is_confirmed


# --- Own hours ------------------------------------------------------------------------------

def test_supervisor_sees_own_day_marked_as_confirmed_by_the_admin(login_as, users, days):
    rows = login_as("supervisor").get(f"/payroll/schedules?start_date={DAY}&end_date={DAY}"
                                      f"&project_id={users['project_id']}").json()
    own = {r["id"]: r["own"] for r in rows}
    assert own == {days["supervisor"]: True, days["worker"]: False}


def test_admin_rows_are_never_marked_own(login_as, users, days):
    rows = login_as("admin").get(f"/payroll/schedules?start_date={DAY}&end_date={DAY}").json()
    assert len(rows) == 2 and not any(r["own"] for r in rows)


def test_approval_page_explains_the_rule_to_the_supervisor(login_as):
    assert "Tus propias horas las confirma el admin" in login_as("supervisor").get("/payroll/approval").text
    assert "own-hours-note" not in login_as("admin").get("/payroll/approval").text


def test_batch_update_skips_the_supervisors_own_day_and_says_so(db, login_as, days):
    body = [{"id": days["supervisor"], "hours": 9}, {"id": days["worker"], "hours": 7}]
    response = login_as("supervisor").post("/payroll/hours/confirm-batch-update", json=body)
    assert response.status_code == 200 and "las confirma el admin" in response.json()["message"]
    assert confirmed(db, days["worker"]) and not confirmed(db, days["supervisor"])


def test_single_confirm_of_own_day_is_refused(db, login_as, days):
    response = login_as("supervisor").post("/payroll/hours/confirm", json={"schedule_id": days["supervisor"],
                                                                            "hours": 8})
    assert response.status_code == 403 and "confirma el admin" in response.json()["detail"]
    assert not confirmed(db, days["supervisor"])


def test_batch_confirm_leaves_own_day_and_other_projects(db, login_as, users, days):
    login_as("supervisor").post("/payroll/hours/confirm-batch", json=list(days.values()))
    assert confirmed(db, days["worker"]) and not confirmed(db, days["supervisor"])


def test_admin_confirms_the_supervisors_day(db, login_as, days):
    response = login_as("admin").post("/payroll/hours/confirm-batch-update",
                                      json=[{"id": days["supervisor"], "hours": 8}])
    assert response.status_code == 200 and confirmed(db, days["supervisor"])


def test_calendar_marks_the_supervisors_own_row_read_only(login_as):
    html = login_as("supervisor").get("/calendar").text
    assert "Tus horas las confirma el admin" in html and "function isOwnRow" in html


# --- Bitácora: what the page says when saving fails -------------------------------------------

def report(client, users):
    return client.post("/logs/new", data={"project_id": users["project_id"], "date": today_cr().isoformat(),
                                          "notes": "Chapea y poda"}, follow_redirects=False)


def test_an_internal_error_answers_with_a_reason_and_saves_nothing(db, login_as, users, monkeypatch):
    def broken(*args, **kwargs):
        raise OSError("disco lleno")
    monkeypatch.setattr(logs_router, "store_photos", broken)
    response = report(login_as("supervisor"), users)
    assert response.status_code == 500
    assert "no pudo guardar el reporte" in response.json()["detail"]
    assert db.query(DailyLog).count() == 0


def test_an_internal_error_while_editing_answers_with_a_reason(db, login_as, users, monkeypatch):
    log = DailyLog(project_id=users["project_id"], user_id=users["worker"].id, date=today_cr(), notes="ok")
    db.add(log)
    db.commit()
    monkeypatch.setattr(logs_router, "store_photos", lambda *a, **k: (_ for _ in ()).throw(OSError("x")))
    response = login_as("worker").post(f"/logs/{log.id}/edit", data={"notes": "nuevo"}, follow_redirects=False)
    assert response.status_code == 500 and "no pudo guardar" in response.json()["detail"]
    db.expire_all()
    assert db.get(DailyLog, log.id).notes == "ok"


def test_the_report_still_saves_normally(db, login_as, users):
    assert report(login_as("supervisor"), users).status_code == 303
    assert db.query(DailyLog).count() == 1


def test_both_forms_shrink_photos_and_never_say_unknown_error(login_as, users):
    client = login_as("supervisor")
    new_form = client.get(f"/logs/new?project_id={users['project_id']}").text
    log_list = client.get("/logs/").text  # includes the report window with Editar
    for html in (new_form, log_list):
        assert "/static/js/photo_upload.js?v=" in html
    assert "TomatoPhotos.shrinkField(formData)" in new_form and "Error desconocido" not in new_form
    assert "TomatoPhotos.failureMessage(response, data)" in log_list


def test_photo_script_explains_each_error_code(login_as):
    script = Path("app/static/js/photo_upload.js").read_text()
    for code in ("error 413", "error 504", "error ${code}"):
        assert code in script
    assert "2048" in script and "image/jpeg" in script
    assert login_as("worker").get("/static/js/photo_upload.js").status_code == 200
