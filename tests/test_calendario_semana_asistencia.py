"""Calendar, phase 1 of the planilla plan: attendance when confirming the day (Asistió, Llegó
tarde, No llegó), the estimated labour cost of the dates on screen, and the week and day views."""
from datetime import date

import pytest

from app.db.models.payroll import PayrollEntry
from app.db.models.schedule import ProjectSchedule
from tests.conftest import make_user


@pytest.fixture
def team(db, users):
    users["worker"].hourly_rate = 2000
    db.commit()
    return [users["worker"].id, make_user(db, "u_worker2", "worker", hourly_rate=1000).id]


def assign(client, users, people, start="2026-09-21", end=None):
    data = {"project_id": users["project_id"], "date": start, "user_ids": people}
    if end:
        data["end_date"] = end
    return client.post("/calendar/schedule", data=data)


def by_user(db):
    db.expire_all()
    return {s.user_id: s for s in db.query(ProjectSchedule)}


def confirm(client, db, attendance, hours=8, overtime=1):
    """attendance: {user_id: value}; everyone else is sent without it."""
    items = [{"id": s.id, "hours": hours, "overtime": overtime,
              **({"attendance": attendance[s.user_id]} if s.user_id in attendance else {})}
             for s in db.query(ProjectSchedule)]
    return client.post("/calendar/day/confirm-hours", json=items)


def test_no_show_is_confirmed_with_zero_hours(db, login_as, users, team):
    client = login_as("admin")
    assign(client, users, team)
    response = confirm(client, db, {team[0]: "no_llego", team[1]: "tarde"})
    assert response.status_code == 200
    rows = by_user(db)
    absent, late = rows[team[0]], rows[team[1]]
    assert absent.is_confirmed and absent.attendance == "no_llego"
    assert absent.hours_worked == 0 and absent.overtime_hours == 0
    assert late.attendance == "tarde" and late.hours_worked == 8 and late.overtime_hours == 1


def test_attendance_defaults_to_asistio(db, login_as, users, team):
    client = login_as("admin")
    assign(client, users, team)
    confirm(client, db, {})
    assert {s.attendance for s in by_user(db).values()} == {"asistio"}


def test_unknown_attendance_is_refused(db, login_as, users, team):
    client = login_as("admin")
    assign(client, users, [team[0]])
    response = confirm(client, db, {team[0]: "vacaciones"})
    assert response.status_code == 400 and "asistencia" in response.json()["message"]
    assert not by_user(db)[team[0]].is_confirmed


def test_events_count_who_did_not_come(db, login_as, users, team):
    client = login_as("admin")
    assign(client, users, team)
    confirm(client, db, {team[0]: "no_llego"})
    event = client.get("/calendar/events?start=2026-09-01&end=2026-09-30").json()[0]
    assert event["extendedProps"]["absent"] == 1
    members = {m["worker_id"]: m for m in event["extendedProps"]["members"]}
    assert members[team[0]]["attendance"] == "no_llego" and members[team[1]]["attendance"] == "asistio"


def test_events_include_the_first_day_of_the_range(login_as, users, team):
    client = login_as("admin")
    assign(client, users, team, start="2026-10-26")
    # What FullCalendar sends for the week that starts on Monday 26/10.
    events = client.get("/calendar/events?start=2026-10-26T00:00:00-06:00&end=2026-11-02T00:00:00-06:00").json()
    assert [e["start"] for e in events] == ["2026-10-26"]
    assert login_as("admin").get("/calendar/events?start=ayer&end=hoy").status_code == 400


def test_hours_given_in_aprobar_horas_undo_a_no_show(db, login_as, users, team):
    client = login_as("admin")
    assign(client, users, team)
    confirm(client, db, {team[0]: "no_llego", team[1]: "no_llego"})
    rows = by_user(db)
    client.post("/payroll/hours/confirm", json={"schedule_id": rows[team[0]].id, "hours": 8, "overtime": 0})
    client.post("/payroll/hours/confirm-batch-update", json=[{"id": rows[team[1]].id, "hours": 0, "overtime": 0}])
    rows = by_user(db)
    assert rows[team[0]].attendance == "asistio" and rows[team[0]].hours_worked == 8
    assert rows[team[1]].attendance == "no_llego"


def test_payroll_breakdown_keeps_attendance(db, login_as, users, team):
    client = login_as("admin")
    assign(client, users, team)
    confirm(client, db, {team[0]: "no_llego"})
    client.post("/payroll/generate", json={"start_date": "2026-09-16", "end_date": "2026-09-30"})
    entry = db.query(PayrollEntry).filter(PayrollEntry.user_id == team[0]).one()
    assert entry.total_hours == 0 and entry.details[0]["attendance"] == "no_llego"


def test_cost_of_the_dates_on_screen(db, login_as, users, team):
    client = login_as("admin")
    # Two days, two people at 8 h planned: 2 × (8 × 2000) + 2 × (8 × 1000) = 48 000.
    assign(client, users, team, end="2026-09-22")
    cost = client.get("/calendar/cost?start=2026-09-21&end=2026-09-23").json()
    assert cost["cost"] == 48000 and cost["hours"] == 32 and cost["pending"] == 48000 and cost["confirmed"] == 0
    # The end is not included: only the 21st.
    assert client.get("/calendar/cost?start=2026-09-21&end=2026-09-22").json()["cost"] == 24000


def test_cost_splits_confirmed_and_skips_no_shows(db, login_as, users, team):
    client = login_as("admin")
    assign(client, users, team)
    # Worker 1 did not come; worker 2: 8 h + 1 h extra at 1000 = 8000 + 1500.
    confirm(client, db, {team[0]: "no_llego", team[1]: "asistio"})
    cost = client.get("/calendar/cost?start=2026-09-21&end=2026-09-22").json()
    assert cost["cost"] == 9500 and cost["confirmed"] == 9500 and cost["pending"] == 0
    assert cost["hours"] == 8 and cost["overtime"] == 1


def test_cost_names_people_without_a_rate(db, login_as, users, team):
    client = login_as("admin")
    no_rate = make_user(db, "u_sin_tarifa", "worker", full_name="Sin Tarifa").id
    assign(client, users, [team[0], no_rate])
    cost = client.get("/calendar/cost?start=2026-09-21&end=2026-09-22").json()
    assert cost["without_rate"] == ["Sin Tarifa"] and cost["cost"] == 16000


@pytest.mark.parametrize("role", ["supervisor", "worker"])
def test_only_admin_sees_the_cost(login_as, role):
    assert login_as(role).get("/calendar/cost?start=2026-09-21&end=2026-09-22").status_code == 403


def test_bad_dates_for_the_cost(login_as):
    assert login_as("admin").get("/calendar/cost?start=ayer&end=hoy").status_code == 400


def test_calendar_page_has_week_day_and_colors(login_as):
    admin = login_as("admin").get("/calendar/").text
    assert "dayGridWeek" in admin and "dayGridDay" in admin and 'id="color-mode"' in admin
    assert 'id="cost-box"' in admin
    supervisor = login_as("supervisor").get("/calendar/").text
    assert 'id="color-mode"' in supervisor and 'id="cost-box"' not in supervisor
    worker = login_as("worker").get("/calendar/").text
    assert 'id="color-mode"' not in worker and 'id="cost-box"' not in worker
