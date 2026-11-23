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
    assert "TomatoPhotos.tooBig(formData)" in new_form and "TomatoPhotos.tooBig(data)" in log_list


def test_photo_script_explains_each_error_code(login_as):
    script = Path("app/static/js/photo_upload.js").read_text()
    for code in ("error 413", "error 504", "error ${code}"):
        assert code in script
    assert "image/jpeg" in script and "MAX_REQUEST_MB = 45" in script
    assert login_as("worker").get("/static/js/photo_upload.js").status_code == 200


# --- One photo optimizer (the one the report e-mail used) and at most 10 photos ---------------

from app.db.models.log import Photo
from app.utils import uploads
from tests.test_ux_ronda_1 import image_bytes


def photo(i=0):
    return ("photos", (f"foto{i}.png", image_bytes(), "image/png"))


def new_report(client, users, count):
    return client.post("/logs/new", data={"project_id": users["project_id"], "date": today_cr().isoformat(),
                                          "notes": "ok"}, files=[photo(i) for i in range(count)],
                       follow_redirects=False)


@pytest.fixture
def uploads_dir(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "app" / "static" / "uploads").mkdir(parents=True)
    return tmp_path


def test_phone_server_and_email_use_the_same_numbers():
    script = Path("app/static/js/photo_upload.js").read_text()
    assert f"MAX_SIDE = {uploads.REPORT_PHOTO_MAX_SIDE};" in script
    assert f"QUALITY = {uploads.REPORT_PHOTO_QUALITY / 100:.2f};" in script
    assert f"MAX_PHOTOS = {uploads.MAX_REPORT_PHOTOS};" in script
    email = Path("app/utils/email.py").read_text()
    assert "REPORT_PHOTO_MAX_SIDE, REPORT_PHOTO_MAX_SIDE" in email and "quality=REPORT_PHOTO_QUALITY" in email


def test_saved_photos_are_at_most_1280_px(db, login_as, users, uploads_dir):
    from PIL import Image
    assert new_report(login_as("worker"), users, 1).status_code == 303
    path = uploads_dir / "app" / db.query(Photo).one().file_path.lstrip("/")
    with Image.open(path) as img:
        assert img.format == "JPEG" and max(img.size) == 1280


def test_ten_photos_save_and_eleven_are_refused(db, login_as, users, uploads_dir):
    client = login_as("worker")
    refused = new_report(client, users, 11)
    assert refused.status_code == 400 and "hasta 10 fotos" in refused.json()["detail"]
    assert db.query(DailyLog).count() == 0
    assert new_report(client, users, 10).status_code == 303 and db.query(Photo).count() == 10


def test_edit_counts_the_photos_the_report_keeps(db, login_as, users, uploads_dir):
    client = login_as("worker")
    new_report(client, users, 9)
    log = db.query(DailyLog).one()
    edit = lambda count, remove=(): client.post(
        f"/logs/{log.id}/edit", data={"notes": "ok", "remove_photos": list(remove)},
        files=[photo(i) for i in range(count)], follow_redirects=False)
    refused = edit(2)
    assert refused.status_code == 400 and "ya tiene 9" in refused.json()["detail"]
    first = db.query(Photo).first().id
    assert edit(2, remove=[first]).status_code == 303
    db.expire_all()
    assert db.query(Photo).count() == 10


def test_an_old_report_with_more_than_ten_can_still_be_edited_without_new_photos(db, login_as, users):
    log = DailyLog(project_id=users["project_id"], user_id=users["worker"].id, date=today_cr(), notes="ok")
    db.add(log)
    db.flush()
    db.add_all([Photo(log_id=log.id, file_path=f"/static/uploads/x{i}.jpg") for i in range(12)])
    db.commit()
    response = login_as("worker").post(f"/logs/{log.id}/edit", data={"notes": "nuevo"}, follow_redirects=False)
    assert response.status_code == 303


def test_forms_show_the_limit(login_as, users):
    client = login_as("worker")
    html = client.get(f"/logs/new?project_id={users['project_id']}").text
    assert "Hasta 10 fotos" in html and "de 10)" in html and "el máximo por reporte" in html
    assert "currentLogData.max_photos" in client.get("/logs/").text


# --- The exception: a supervisor the admin marked "Confirma sus propias horas" ----------------

from app.db.models.activity import ActivityLog  # noqa: E402
from app.db.models.user import User  # noqa: E402


@pytest.fixture
def exception(db, users):
    users["supervisor"].confirms_own_hours = True
    db.commit()
    return users["supervisor"]


def test_the_exception_confirms_own_hours_everywhere(db, login_as, users, days, exception):
    client = login_as("supervisor")
    rows = client.get(f"/payroll/schedules?start_date={DAY}&end_date={DAY}").json()
    assert not any(r["own"] for r in rows)
    assert "own-hours-note" not in client.get("/payroll/approval").text
    assert "const OWN_HOURS_USER_ID = null" in client.get("/calendar").text
    response = client.post("/payroll/hours/confirm-batch-update", json=[{"id": days["supervisor"], "hours": 9}])
    assert "1 registros confirmados" == response.json()["message"] and confirmed(db, days["supervisor"])


def test_the_exception_confirms_own_day_from_the_calendar(db, login_as, days, exception):
    response = login_as("supervisor").post("/calendar/day/confirm-hours",
                                           json=[{"id": days["supervisor"], "hours": 8, "overtime": 0}])
    assert response.status_code == 200 and confirmed(db, days["supervisor"])


def test_the_exception_still_only_covers_own_projects(db, login_as, users, exception):
    from app.db.models.project import Project
    other = Project(name="Otro", is_active=True)
    db.add(other)
    db.flush()
    row = ProjectSchedule(project_id=other.id, user_id=exception.id, date=DAY, hours_worked=8, is_confirmed=False)
    db.add(row)
    db.commit()
    assert login_as("supervisor").post("/payroll/hours/confirm", json={"schedule_id": row.id, "hours": 8}).status_code == 403


def test_other_supervisors_keep_the_rule(db, users, exception):
    from app.db.models.project import Project
    from tests.conftest import login, make_user, new_client
    other = make_user(db, "u_sup2", "supervisor")
    project = db.get(Project, users["project_id"])
    project.users.append(other)
    row = ProjectSchedule(project_id=users["project_id"], user_id=other.id, date=DAY, hours_worked=8, is_confirmed=False)
    db.add(row)
    db.commit()
    client = new_client()
    login(client, "u_sup2")
    assert client.post("/payroll/hours/confirm", json={"schedule_id": row.id, "hours": 8}).status_code == 403
    assert "own-hours-note" in client.get("/payroll/approval").text


def test_admin_sets_the_exception_only_for_supervisors_and_it_goes_to_activity(db, login_as, users):
    admin = login_as("admin")
    form = {"password": "clave-segura", "full_name": "Will", "email": "w@example.com", "payment_method": "Efectivo",
            "is_active": "true", "confirms_own_hours": "true"}
    admin.post("/users/new", data={**form, "username": "will", "role": "supervisor"}, follow_redirects=False)
    admin.post("/users/new", data={**form, "username": "trab3", "role": "worker", "email": "t@example.com"},
               follow_redirects=False)
    assert db.query(User).filter_by(username="will").one().confirms_own_hours is True
    assert db.query(User).filter_by(username="trab3").one().confirms_own_hours is False
    sup = users["supervisor"]
    edit = {"username": sup.username, "full_name": "Supervisor", "email": "s@example.com", "role": "supervisor",
            "payment_method": "Efectivo", "is_active": "true", "confirms_own_hours": "true"}
    admin.post(f"/users/{sup.id}/edit", data=edit, follow_redirects=False)
    db.expire_all()
    assert db.get(User, sup.id).confirms_own_hours is True
    assert db.query(ActivityLog).filter(ActivityLog.details.contains("ahora confirma sus propias horas")).count() == 1
    assert "Confirma sus propias horas" in admin.get(f"/users/{sup.id}/edit").text
