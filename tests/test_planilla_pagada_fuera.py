"""An approved quincena paid without recording the payments here can be marked as paid outside
the system: it counts as Pagada, with who and when, and it can be undone."""
from datetime import date

import pytest

from app.db.models.payroll import PayrollEntry, PayrollPeriod
from app.db.models.schedule import ProjectSchedule


@pytest.fixture
def approved(db, login_as, users):
    users["worker"].hourly_rate = 2000
    db.add(ProjectSchedule(project_id=users["project_id"], user_id=users["worker"].id, date=date(2026, 1, 13),
                           hours_worked=8, is_confirmed=True))
    db.commit()
    client = login_as("admin")
    period_id = client.post("/payroll/generate", json={"start_date": "2026-01-13", "end_date": "2026-01-17"}).json()["period_id"]
    return client, period_id


def test_mark_paid_outside_and_undo(db, approved, users):
    client, period_id = approved
    assert client.post(f"/payroll/{period_id}/paid-outside").status_code == 400  # a draft first gets approved
    client.post("/payroll/confirm", json={"period_id": period_id})
    page = client.get("/payroll/").text
    assert "1 por pagar" in page
    assert client.post(f"/payroll/{period_id}/paid-outside").status_code == 200
    db.expire_all()
    period = db.get(PayrollPeriod, period_id)
    assert period.paid_outside_at is not None and period.paid_outside_by_id == users["admin"].id
    page = client.get("/payroll/").text
    assert "fuera del sistema" in page and "por pagar" not in page and "Pagos al día" in page
    detail = client.get(f"/payroll/detail/{period_id}").text
    assert "Pagada fuera del sistema" in detail and "Deshacer" in detail
    # Already paid: no second mark, and no payment on top of it.
    assert client.post(f"/payroll/{period_id}/paid-outside").status_code == 400
    entry = db.query(PayrollEntry).one()
    paid = client.post(f"/payroll/entry/{entry.id}/pay", json={"date": "2026-01-20", "method": "Sinpe"})
    assert paid.status_code == 400 and "Deshacé" in paid.json()["detail"]
    assert client.post(f"/payroll/{period_id}/paid-outside/undo").status_code == 200
    assert "1 por pagar" in client.get("/payroll/").text
    assert client.post(f"/payroll/{period_id}/paid-outside/undo").status_code == 400


def test_mark_is_recorded_in_activity(db, approved):
    from app.db.models.activity import ActivityLog
    client, period_id = approved
    client.post("/payroll/confirm", json={"period_id": period_id})
    client.post(f"/payroll/{period_id}/paid-outside")
    assert db.query(ActivityLog).filter(ActivityLog.action == "Pagada fuera del sistema").count() == 1


@pytest.mark.parametrize("role", ["supervisor", "worker", "ventas"])
def test_only_admin_marks(approved, login_as, role):
    _, period_id = approved
    assert login_as(role).post(f"/payroll/{period_id}/paid-outside").status_code == 403
    assert login_as(role).post(f"/payroll/{period_id}/paid-outside/undo").status_code == 403
