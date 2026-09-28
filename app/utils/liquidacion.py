"""Liquidación laboral according to the Costa Rican Código de Trabajo. It is an estimate
for the admin and the accountant to review; every amount can be corrected in the screen
before confirming. Rules:

- Aguinaldo (Ley 2412): 1/12 of the salaries earned since the last 1 December (or the start
  date, if later) up to the end date. It uses the final payrolls of that window and fills
  the months without one with the average salary.
- Vacaciones (arts. 153 and 156): 1 day per month worked, minus the days already taken,
  paid at the average daily salary.
- Preaviso (art. 28), only when the employer ends the contract without just cause and
  did not give notice: 3-6 months → 7 days, 6-12 months → 15 days, 1 year or more → 30 days.
- Cesantía (art. 29), only when the employer ends the contract without just cause:
  3-6 months → 7 days, 6-12 months → 14 days, 1 year or more → the table below per year
  worked, at most 8 years.
- Average salary (art. 30): the final payrolls of the last 6 months; without payrolls,
  the monthly salary. Daily salary = monthly average / 30.
- Pending salary: confirmed calendar hours after the last payment (overtime × 1.5);
  without them, 8 h per weekday.
- Worker CCSS (9.17 %) is withheld from pending salary and vacation pay only, when the
  person has "Aplicar Deducciones"; aguinaldo, preaviso and cesantía don't carry it.
"""
from dataclasses import asdict, dataclass
from datetime import date, timedelta
from typing import Dict, List, Optional, Tuple

REASONS = {
    "renuncia": "Renuncia del trabajador",
    "despido_con_responsabilidad": "Despido con responsabilidad patronal (sin justa causa)",
    "despido_sin_responsabilidad": "Despido sin responsabilidad patronal (con justa causa, art. 81)",
}
PAYS_EMPLOYER_TERMINATION = "despido_con_responsabilidad"
# Art. 29: days per year worked, by total years of service.
CESANTIA_DAYS_PER_YEAR = {1: 19.5, 2: 20, 3: 20.5, 4: 21, 5: 21.24, 6: 21.5, 7: 22, 8: 22, 9: 22, 10: 21.5,
                          11: 21, 12: 20.5}
CESANTIA_MAX_YEARS = 8
CCSS_WORKER_RATE = 0.0917
DAYS_PER_MONTH = 365 / 12


@dataclass
class Liquidacion:
    start_date: date
    end_date: date
    reason: str
    months_worked: float
    average_monthly_salary: float
    average_basis: str
    daily_salary: float
    vacation_days_earned: float
    vacation_days_taken: float
    vacation_days: float
    vacation_amount: float
    aguinaldo_start: date
    aguinaldo_base: float
    aguinaldo_basis: str
    aguinaldo_amount: float
    preaviso_days: float
    preaviso_amount: float
    cesantia_days: float
    cesantia_amount: float
    salary_due: float
    salary_due_basis: str
    ccss_deduction: float
    total: float

    def as_dict(self) -> Dict:
        data = asdict(self)
        for key in ("start_date", "end_date", "aguinaldo_start"):
            data[key] = data[key].isoformat()
        return data


def months_between(start: date, end: date) -> float:
    return max(0.0, ((end - start).days + 1) / DAYS_PER_MONTH)


def last_december_first(end: date) -> date:
    return date(end.year if end.month == 12 else end.year - 1, 12, 1)


def preaviso_days(months: float) -> float:
    if months < 3:
        return 0
    if months < 6:
        return 7
    if months < 12:
        return 15
    return 30


def cesantia_days(months: float) -> float:
    if months < 3:
        return 0
    if months < 6:
        return 7
    if months < 12:
        return 14
    years = months / 12
    rate = CESANTIA_DAYS_PER_YEAR.get(int(years), 20)
    return round(rate * min(years, CESANTIA_MAX_YEARS), 2)


def weekdays(first: date, last: date) -> int:
    count, day = 0, first
    while day <= last:
        count += day.weekday() < 5
        day += timedelta(days=1)
    return count


def calculate(start: date, end: date, reason: str, monthly_salary: float, hourly_rate: float,
              payrolls: List[Tuple[date, date, float]], pending_hours: Optional[Tuple[float, float]],
              unpaid_from: date, vacation_days_taken: float = 0, notice_given: bool = False,
              apply_deductions: bool = True) -> Liquidacion:
    """payrolls: (period start, period end, gross) of the person's final payrolls.
    pending_hours: (hours, overtime) confirmed after the last payment, or None if unknown."""
    if reason not in REASONS:
        raise ValueError("Motivo de salida no válido")
    if end < start:
        raise ValueError("La fecha de liquidación es anterior a la de inicio")
    monthly_salary, hourly_rate = monthly_salary or 0.0, hourly_rate or 0.0
    months = months_between(start, end)

    # Average salary of the last 6 months (art. 30).
    six_months_ago = max(start, end - timedelta(days=round(6 * DAYS_PER_MONTH)))
    recent = [(s, e, g) for s, e, g in payrolls if e >= six_months_ago and s <= end]
    if recent:
        covered = months_between(max(six_months_ago, min(s for s, _, _ in recent)), min(end, max(e for _, e, _ in recent)))
        average = sum(g for _, _, g in recent) / max(covered, 0.5)
        average_basis = f"planillas de los últimos {min(6, round(covered, 1))} meses"
    else:
        average = monthly_salary or hourly_rate * 8 * weekdays(end - timedelta(days=29), end)
        average_basis = "salario mensual del perfil" if monthly_salary else "tarifa por hora del perfil"
    daily = average / 30

    # Pending salary.
    rate = hourly_rate or (monthly_salary / 30 / 8 if monthly_salary else 0.0)
    if pending_hours is not None:
        hours, overtime = pending_hours
        salary_due = hours * rate + overtime * rate * 1.5
        salary_due_basis = f"{hours:g} h y {overtime:g} h extra confirmadas sin pagar"
    else:
        days = weekdays(unpaid_from, end) if unpaid_from <= end else 0
        salary_due = days * 8 * rate
        salary_due_basis = f"{days} días hábiles × 8 h desde el último pago (sin horas confirmadas)"

    # Vacaciones.
    earned = months
    vacation_days = max(0.0, earned - (vacation_days_taken or 0))
    vacation_amount = vacation_days * daily

    # Aguinaldo: salaries earned since 1 December. Final payrolls count as they are; the
    # months without one (a history kept outside the system, or the days not yet paid)
    # are filled with the average salary, so a partial history never lowers it.
    window_start = max(start, last_december_first(end))
    window_months = months_between(window_start, end)
    in_window = [(max(s, window_start), min(e, end), g) for s, e, g in payrolls if e >= window_start and s <= end]
    covered_days = set()
    for s, e, _ in in_window:
        covered_days.update(s + timedelta(days=i) for i in range((e - s).days + 1))
    covered = len(covered_days) / DAYS_PER_MONTH
    uncovered = max(0.0, window_months - covered)
    payroll_gross = sum(g for _, _, g in in_window)
    aguinaldo_base = payroll_gross + average * uncovered
    if in_window:
        aguinaldo_basis = (f"planillas de {covered:.1f} meses + salario promedio × {uncovered:.1f} meses sin planilla"
                           if uncovered >= 0.05 else "planillas desde el 1 de diciembre")
    else:
        aguinaldo_basis = f"salario promedio × {window_months:.1f} meses desde el 1 de diciembre (sin planillas)"
    aguinaldo = aguinaldo_base / 12

    employer_ends = reason == PAYS_EMPLOYER_TERMINATION
    p_days = preaviso_days(months) if employer_ends and not notice_given else 0
    c_days = cesantia_days(months) if employer_ends else 0

    ccss = (salary_due + vacation_amount) * CCSS_WORKER_RATE if apply_deductions else 0.0
    total = salary_due + vacation_amount + aguinaldo + p_days * daily + c_days * daily - ccss
    r = lambda x: round(x, 2)  # noqa: E731
    return Liquidacion(
        start_date=start, end_date=end, reason=reason, months_worked=r(months),
        average_monthly_salary=r(average), average_basis=average_basis, daily_salary=r(daily),
        vacation_days_earned=r(earned), vacation_days_taken=r(vacation_days_taken or 0), vacation_days=r(vacation_days),
        vacation_amount=r(vacation_amount), aguinaldo_start=window_start, aguinaldo_base=r(aguinaldo_base),
        aguinaldo_basis=aguinaldo_basis, aguinaldo_amount=r(aguinaldo), preaviso_days=p_days,
        preaviso_amount=r(p_days * daily), cesantia_days=c_days, cesantia_amount=r(c_days * daily),
        salary_due=r(salary_due), salary_due_basis=salary_due_basis, ccss_deduction=r(ccss), total=r(total),
    )
