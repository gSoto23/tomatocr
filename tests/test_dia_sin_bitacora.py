"""«No ocupa bitácora»: a project's day that legitimately has no report stops counting in
«días trabajados sin bitácora». It is marked from the Dashboard alert or the day in the Calendario,
it can be undone, and both leave their trace in Actividad."""
from datetime import timedelta

from app.db.models.activity import ActivityLog
from app.db.models.log import DailyLog, LogExemption
from app.db.models.schedule import ProjectSchedule
from app.utils.admin_overview import admin_overview, missing_reports
from app.utils.timecr import today_cr

JSON = {"Accept": "application/json"}


def worked(db, users, days_ago, who="worker"):
    day = today_cr() - timedelta(days=days_ago)
    db.add(ProjectSchedule(project_id=users["project_id"], user_id=users[who].id, date=day))
    db.commit()
    return day


def alert(db):
    return next((a for a in admin_overview(db, today_cr()).alerts if a.key == "sin_bitacora"), None)


def test_marked_day_leaves_the_alert_and_the_alert_goes_when_none_is_left(db, users, login_as):
    first, second = worked(db, users, 2), worked(db, users, 3)
    assert alert(db).title == "2 días trabajados sin bitácora"
    client = login_as("admin")
    response = client.post("/logs/no-ocupa", follow_redirects=False,
                           data={"project_id": users["project_id"], "date": first.isoformat(), "reason": "  Llovió   todo el día ",
                                 "next": "/dashboard/"})
    assert response.status_code == 303 and response.headers["location"] == "/dashboard/"
    assert "Listo:" in response.cookies.get("toast_message", "")
    mark = db.query(LogExemption).one()
    assert (mark.date, mark.reason, mark.user_id) == (first, "Llovió todo el día", users["admin"].id)
    assert alert(db).title == "1 día trabajado sin bitácora"
    assert [d["date"] for d in alert(db).days] == [second]

    client.post("/logs/no-ocupa", data={"project_id": users["project_id"], "date": second.isoformat()})
    assert alert(db) is None
    assert "trabajado sin bitácora" not in client.get("/dashboard/").text


def test_undo_brings_the_day_back_and_both_are_in_activity(db, users, login_as):
    day = worked(db, users, 1)
    client = login_as("supervisor")
    data = {"project_id": users["project_id"], "date": day.isoformat(), "reason": "Solo entrega"}
    assert client.post("/logs/no-ocupa", data=data, headers=JSON).json()["status"] == "success"
    assert missing_reports(db, today_cr()) == []
    answer = client.post("/logs/no-ocupa/deshacer", data=data, headers=JSON).json()
    assert answer["status"] == "success" and "vuelve a pedir bitácora" in answer["message"]
    assert db.query(LogExemption).count() == 0
    assert missing_reports(db, today_cr()) == [(users["project_id"], day)]
    marks = db.query(ActivityLog).filter(ActivityLog.action.in_(["NO_REPORT", "UNDO_NO_REPORT"])).order_by(ActivityLog.id).all()
    assert [(a.action, a.user_id) for a in marks] == [("NO_REPORT", users["supervisor"].id), ("UNDO_NO_REPORT", users["supervisor"].id)]
    details = [a.details for a in marks]
    assert "Motivo: Solo entrega" in details[0] and "Deshizo" in details[1]


def test_worker_reminder_also_drops_the_day(db, users, login_as):
    day = worked(db, users, 2)
    assert "Te quedó 1 día sin bitácora" in login_as("worker").get("/dashboard/").text
    login_as("admin").post("/logs/no-ocupa", data={"project_id": users["project_id"], "date": day.isoformat()})
    assert "Te quedó" not in login_as("worker").get("/dashboard/").text


def test_only_admin_and_supervisor_and_only_sensible_days(db, users, login_as):
    day = worked(db, users, 2)
    data = {"project_id": users["project_id"], "date": day.isoformat()}
    assert login_as("worker").post("/logs/no-ocupa", data=data, headers=JSON).status_code == 403
    assert login_as("client").post("/logs/no-ocupa", data=data, headers=JSON).status_code == 403
    admin = login_as("admin")
    future = {**data, "date": (today_cr() + timedelta(days=1)).isoformat()}
    assert "todavía no pasó" in admin.post("/logs/no-ocupa", data=future, headers=JSON).json()["message"]
    assert admin.post("/logs/no-ocupa", data={**data, "project_id": 999}, headers=JSON).status_code == 400
    db.add(DailyLog(project_id=users["project_id"], user_id=users["worker"].id, date=day, notes="ok"))
    db.commit()
    assert admin.post("/logs/no-ocupa", data=data, headers=JSON).json()["message"] == "Ese día ya tiene bitácora"
    assert db.query(LogExemption).count() == 0
    # An outside "next" never leaves the system.
    response = admin.post("/logs/no-ocupa/deshacer", data={**data, "next": "//evil.example"}, follow_redirects=False)
    assert response.headers["location"] == "/dashboard/"


def test_dashboard_lists_each_day_with_its_actions(db, users, login_as):
    day = worked(db, users, 2)
    html = login_as("admin").get("/dashboard/").text
    assert 'action="/logs/no-ocupa"' in html and 'data-confirm-input="reason"' in html
    assert f'name="date" value="{day.isoformat()}"' in html
    assert f"/logs/new?project_id={users['project_id']}&amp;date={day.isoformat()}" in html
    assert "No ocupa bitácora" in html
    # The worker registers their days; they don't mark them.
    assert 'action="/logs/no-ocupa"' not in login_as("worker").get("/dashboard/").text


def test_today_in_the_field_says_no_report_needed(db, users, login_as):
    today = worked(db, users, 0)
    login_as("admin").post("/logs/no-ocupa", data={"project_id": users["project_id"], "date": today.isoformat()})
    ov = admin_overview(db, today_cr())
    assert ov.in_field[0].exempt and not ov.in_field[0].reported


def test_calendar_day_carries_the_report_state(db, users, login_as):
    day = worked(db, users, 2)
    client = login_as("admin")
    client.post("/logs/no-ocupa", data={"project_id": users["project_id"], "date": day.isoformat(), "reason": "Llovió"})
    events = client.get(f"/calendar/events?start={day.isoformat()}&end={(day + timedelta(days=1)).isoformat()}").json()
    props = events[0]["extendedProps"]
    assert props["has_log"] is False
    assert props["no_report"]["reason"] == "Llovió" and props["no_report"]["by"] == users["admin"].full_name
    html = client.get("/calendar/").text
    assert 'id="day-report"' in html and "/logs/no-ocupa/deshacer" in html


def test_confirm_window_takes_an_optional_text():
    from pathlib import Path
    text = (Path(__file__).resolve().parents[1] / "app/templates/components/confirm_modal.html").read_text()
    assert 'id="tomato-confirm-input"' in text and "form.dataset.confirmInput" in text
