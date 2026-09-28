"""Liquidación per the Código de Trabajo (app/utils/liquidacion.py) and its screens."""
from datetime import date

import pytest

from app.db.models.liquidation import Liquidation
from app.db.models.payroll import PayrollEntry, PayrollPeriod
from app.db.models.schedule import ProjectSchedule
from app.db.models.user import User
from app.utils.liquidacion import calculate, cesantia_days, last_december_first, preaviso_days

END = date(2026, 9, 27)


def calc(start, reason="renuncia", salary=400000, rate=2100, payrolls=(), pending=None, **kw):
    return calculate(start, END, reason, salary, rate, list(payrolls), pending, kw.pop("unpaid_from", END), **kw)


@pytest.mark.parametrize("months,preaviso,cesantia", [
    (2, 0, 0), (4, 7, 7), (8, 15, 14), (13, 30, 19.5 * 13 / 12), (30, 30, 20 * 30 / 12), (120, 30, 21.5 * 8),
])
def test_preaviso_and_cesantia_tables(months, preaviso, cesantia):
    assert preaviso_days(months) == preaviso
    assert cesantia_days(months) == pytest.approx(cesantia, abs=0.01)


def test_aguinaldo_window_starts_on_the_last_december_first():
    assert last_december_first(date(2026, 9, 27)) == date(2025, 12, 1)
    assert last_december_first(date(2026, 12, 15)) == date(2026, 12, 1)


def test_resignation_pays_salary_vacation_and_aguinaldo_only():
    r = calc(date(2024, 9, 28), vacation_days_taken=10)
    assert r.months_worked == pytest.approx(24.0, abs=0.1)
    assert r.vacation_days == pytest.approx(r.vacation_days_earned - 10)
    assert r.vacation_amount == pytest.approx(r.vacation_days * 400000 / 30, abs=0.5)
    # 1 Dec 2025 → 27 Sep 2026 ≈ 9.9 months of salary, divided by 12.
    assert r.aguinaldo_start == date(2025, 12, 1)
    assert r.aguinaldo_amount == pytest.approx(400000 * ((END - date(2025, 12, 1)).days + 1) / (365 / 12) / 12, abs=1)
    assert (r.preaviso_amount, r.cesantia_amount) == (0, 0)


def test_employer_termination_adds_preaviso_and_cesantia():
    r = calc(date(2024, 9, 28), reason="despido_con_responsabilidad")
    assert r.preaviso_days == 30 and r.preaviso_amount == pytest.approx(30 * 400000 / 30)
    assert r.cesantia_days == pytest.approx(20 * r.months_worked / 12, abs=0.01)
    with_notice = calc(date(2024, 9, 28), reason="despido_con_responsabilidad", notice_given=True)
    assert with_notice.preaviso_amount == 0 and with_notice.cesantia_amount == r.cesantia_amount


def test_dismissal_with_just_cause_pays_neither():
    r = calc(date(2024, 9, 28), reason="despido_sin_responsabilidad")
    assert (r.preaviso_amount, r.cesantia_amount) == (0, 0)


def test_ccss_only_on_salary_and_vacation():
    r = calc(date(2025, 9, 28), pending=(40, 2))
    assert r.salary_due == pytest.approx(40 * 2100 + 2 * 2100 * 1.5)
    assert r.ccss_deduction == pytest.approx((r.salary_due + r.vacation_amount) * 0.0917, abs=0.02)
    assert r.total == pytest.approx(r.salary_due + r.vacation_amount + r.aguinaldo_amount - r.ccss_deduction, abs=0.05)
    assert calc(date(2025, 9, 28), apply_deductions=False).ccss_deduction == 0


def test_payrolls_feed_the_average_and_the_aguinaldo():
    payrolls = [(date(2026, 8, 1), date(2026, 8, 31), 450000), (date(2026, 9, 1), date(2026, 9, 27), 450000)]
    r = calc(date(2025, 1, 6), payrolls=payrolls, pending=(0, 0))
    assert "planillas" in r.average_basis and r.average_monthly_salary > 400000
    # Aug–Sep come from the payrolls; Dec–Jul (no payroll) at the average salary.
    covered = 58 / (365 / 12)
    window = ((END - date(2025, 12, 1)).days + 1) / (365 / 12)
    assert r.aguinaldo_base == pytest.approx(900000 + r.average_monthly_salary * (window - covered), rel=0.001)
    assert "sin planilla" in r.aguinaldo_basis


def test_a_partial_payroll_history_never_lowers_the_aguinaldo():
    one_fortnight = [(date(2026, 9, 1), date(2026, 9, 15), 200000)]
    with_history = calc(date(2025, 1, 6), payrolls=one_fortnight, pending=(0, 0))
    without = calc(date(2025, 1, 6), salary=0, rate=2100 * 2, payrolls=[], pending=(0, 0))
    assert with_history.aguinaldo_amount > 300000  # ~10 months of salary / 12, not just one fortnight
    assert without.aguinaldo_amount > 0


def test_pending_salary_without_hours_counts_weekdays():
    r = calc(date(2025, 1, 6), unpaid_from=date(2026, 9, 21))  # Mon 21 → Sun 27: 5 weekdays
    assert r.salary_due == pytest.approx(5 * 8 * 2100)


def test_pending_salary_is_left_to_type_when_the_last_record_is_old():
    r = calc(date(2025, 1, 6), unpaid_from=date(2026, 2, 16))
    assert r.salary_due == 0 and "15/02/2026" in r.salary_due_basis
    recent = calc(date(2025, 1, 6), unpaid_from=date(2026, 8, 28))  # 31 days: still estimated
    assert recent.salary_due > 0


def test_pending_salary_is_left_to_type_when_nothing_was_ever_recorded():
    r = calc(date(2025, 1, 6), unpaid_from=None)
    assert r.salary_due == 0 and "escribí el salario pendiente" in r.salary_due_basis


def test_screen_counts_pending_salary_only_after_the_last_final_payroll(db, login_as, users):
    w = db.get(User, users["worker"].id)
    w.start_date, w.monthly_salary, w.hourly_rate = date(2025, 1, 6), 400000, 2100
    db.commit()
    client = login_as("admin")
    nothing = client.get(f"/liquidation/preview/{w.id}", params={"calculation_date": "2026-09-27"}).json()
    assert nothing["salary_due"] == 0 and "escribí" in nothing["salary_due_basis"]
    period = PayrollPeriod(start_date=date(2026, 9, 1), end_date=date(2026, 9, 15), status="final")
    db.add(period)
    db.flush()
    db.add(PayrollEntry(payroll_period_id=period.id, user_id=w.id, total_hours=80, gross_salary=168000))
    db.commit()
    after = client.get(f"/liquidation/preview/{w.id}", params={"calculation_date": "2026-09-27"}).json()
    assert after["salary_due"] == 8 * 8 * 2100  # 16–27 Sep: 8 weekdays, no confirmed hours


@pytest.mark.parametrize("reason,start", [("otra", date(2025, 1, 1)), ("renuncia", date(2027, 1, 1))])
def test_invalid_input(reason, start):
    with pytest.raises(ValueError):
        calc(start, reason=reason)


# --- Screens -------------------------------------------------------------------------------

@pytest.fixture
def worker(db, users):
    w = db.get(User, users["worker"].id)
    w.start_date, w.monthly_salary, w.hourly_rate = date(2024, 9, 28), 400000, 2100
    period = PayrollPeriod(start_date=date(2026, 9, 1), end_date=date(2026, 9, 15), status="final")
    db.add(period)
    db.flush()
    db.add(PayrollEntry(payroll_period_id=period.id, user_id=w.id, total_hours=88, gross_salary=184800,
                        social_charges=16900, net_salary=167900))
    db.add(ProjectSchedule(project_id=users["project_id"], user_id=w.id, date=date(2026, 9, 25), hours_worked=8,
                           is_confirmed=True))
    db.commit()
    return w


def test_preview(login_as, worker):
    body = login_as("admin").get(f"/liquidation/preview/{worker.id}", params={
        "calculation_date": "2026-09-27", "reason": "despido_con_responsabilidad", "vacation_days_taken": "5"}).json()
    assert body["preaviso_days"] == 30 and body["cesantia_amount"] > 0 and body["vacation_days_taken"] == 5
    assert "confirmadas" in body["salary_due_basis"]


def test_preview_without_start_date_says_what_to_do(db, login_as, users):
    response = login_as("admin").get(f"/liquidation/preview/{users['supervisor'].id}")
    assert response.status_code == 400 and "fecha de inicio" in response.json()["detail"]


def test_letter_has_the_company_legal_data_and_the_corrected_amounts(login_as, worker):
    html = login_as("admin").get(f"/liquidation/letter/{worker.id}", params={
        "calculation_date": "2026-09-27", "reason": "renuncia", "salary_due": "12345.67", "total": "99999"}).text
    assert "TOMATO COSTA RICA ANY S.R.L." in html and "3-102-876296" in html and "7080-8613" in html
    assert "3-101-876296" not in html and "80708316" not in html
    assert "Alajuela, 27 de septiembre de 2026" in html
    assert "₡12,345.67" in html and "₡99,999.00" in html


def test_confirm_recomputes_the_total_and_deactivates(db, login_as, worker):
    response = login_as("admin").post("/liquidation/create", data={
        "user_id": worker.id, "date": "2026-09-27", "reason": "despido_con_responsabilidad", "notice_given": "true",
        "vacation_days": 19, "vacation_amount": 250000, "aguinaldo_amount": 300000, "preaviso_amount": 0,
        "cesantia_amount": 540000, "salary_due": 16800, "ccss_deduction": 24500, "total": 1}, follow_redirects=False)
    assert response.status_code == 303
    db.expire_all()
    liq = db.query(Liquidation).one()
    assert liq.total_amount == 250000 + 300000 + 540000 + 16800 - 24500
    assert (liq.reason, liq.notice_given, liq.cesantia_amount) == ("despido_con_responsabilidad", True, 540000)
    assert db.get(User, worker.id).status == "liquidated"


def test_history_page_opens(login_as, worker):
    html = login_as("admin").get(f"/liquidation/history/{worker.id}").text
    assert "Motivo de la salida" in html and "Días de vacaciones ya disfrutados" in html
