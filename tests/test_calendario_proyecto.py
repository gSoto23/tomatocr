"""Calendar by project: one event per project and day with its people inside, assigning
several people at once, confirming the day's hours and moving the whole day."""
from datetime import date

import pytest

from app.db.models.payroll import PayrollPeriod
from app.db.models.schedule import ProjectSchedule
from app.db.models.user import User
from tests.conftest import make_user


@pytest.fixture
def team(db, users):
    return [users["worker"].id, users["supervisor"].id, make_user(db, "u_worker2", "worker").id]


def assign(client, users, people, start="2026-09-21", end=None, **extra):
    data = {"project_id": users["project_id"], "date": start, "user_ids": people}
    if end:
        data["end_date"] = end
    data.update(extra)
    return client.post("/calendar/schedule", data=data)


def test_assign_several_people_and_see_one_event_per_day(db, login_as, users, team):
    client = login_as("admin")
    response = assign(client, users, team, end="2026-09-22")
    assert response.status_code == 200 and "6 asignaciones" in response.json()["message"]
    events = client.get("/calendar/events?start=2026-09-01&end=2026-09-30").json()
    assert len(events) == 2 and all(len(e["extendedProps"]["members"]) == 3 for e in events)
    assert events[0]["title"].endswith("3 personas") and "url" not in events[0]


def test_assign_needs_someone(login_as, users):
    response = login_as("admin").post("/calendar/schedule", data={"project_id": users["project_id"],
                                                                   "date": "2026-09-21"})
    assert response.status_code == 400 and "persona" in response.json()["message"]


def test_worker_sees_only_own_days_without_broken_links(login_as, users, team):
    assign(login_as("admin"), users, team)
    events = login_as("worker").get("/calendar/events?start=2026-09-01&end=2026-09-30").json()
    assert len(events) == 1 and "url" not in events[0]
    assert events[0]["extendedProps"]["url"] == f"/projects/{users['project_id']}"


def day_items(db, hours=6, overtime=1):
    return [{"id": s.id, "hours": hours, "overtime": overtime} for s in db.query(ProjectSchedule)]


def test_supervisor_confirms_the_day_but_not_own_hours(db, login_as, users, team):
    assign(login_as("admin"), users, team)
    response = login_as("supervisor").post("/calendar/day/confirm-hours", json=day_items(db))
    assert response.status_code == 200 and "tus propias horas" in response.json()["message"]
    db.expire_all()
    rows = {s.user_id: s for s in db.query(ProjectSchedule)}
    assert not rows[users["supervisor"].id].is_confirmed
    assert rows[users["worker"].id].is_confirmed and rows[users["worker"].id].overtime_hours == 1
    events = login_as("admin").get("/calendar/events?start=2026-09-01&end=2026-09-30").json()
    assert events[0]["extendedProps"]["all_confirmed"] is False


def test_a_day_in_a_final_payroll_is_closed(db, login_as, users, team):
    assign(login_as("admin"), users, team)
    db.add(PayrollPeriod(start_date=date(2026, 9, 16), end_date=date(2026, 9, 30), status="final"))
    db.commit()
    response = login_as("admin").post("/calendar/day/confirm-hours", json=day_items(db))
    assert response.status_code == 400 and "planilla final" in response.json()["message"]


def test_drag_moves_the_whole_day(db, login_as, users, team):
    client = login_as("admin")
    assign(client, users, team)
    moved = client.post("/calendar/day/move", data={"project_id": users["project_id"], "from_date": "2026-09-21",
                                                    "to_date": "2026-09-23"})
    assert moved.status_code == 200
    assert {s.date for s in db.query(ProjectSchedule)} == {date(2026, 9, 23)}
    client.post("/calendar/day/confirm-hours", json=day_items(db))
    blocked = client.post("/calendar/day/move", data={"project_id": users["project_id"], "from_date": "2026-09-23",
                                                      "to_date": "2026-09-24"})
    assert blocked.status_code == 400


def test_moving_onto_a_busy_day_asks_first(db, login_as, users, team):
    client = login_as("admin")
    assign(client, users, team)
    assign(client, users, [team[0]], start="2026-09-24")
    busy = client.post("/calendar/day/move", data={"project_id": users["project_id"], "from_date": "2026-09-21",
                                                   "to_date": "2026-09-24"})
    assert busy.status_code == 409
    ok = client.post("/calendar/day/move", data={"project_id": users["project_id"], "from_date": "2026-09-21",
                                                 "to_date": "2026-09-24", "confirm_conflicts": "true"})
    assert ok.status_code == 200
