"""Payroll rules by pay type (docs/PLAN_PLANILLA_CALENDARIO.md, Fase 2).

The payroll is paid by quincena (1–15 and 16–end of month). A monthly salary pays half per
quincena; a partial quincena (hired in the middle, or a period that covers only part of it)
pays the share of its days.
"""
import calendar
from datetime import date, timedelta
from typing import Optional

PAY_TYPES = {"hora": "Por hora", "dia": "Por día", "mensual": "Mensual"}
EMPLOYMENT_TYPES = {"fijo": "Fijo", "ocasional": "Ocasional"}
# A month of 48-hour weeks, the same rule the employee form uses to suggest the hourly rate.
HOURS_PER_MONTH = 192


def quincena_of(day: date) -> tuple:
    """First and last day of the quincena that holds `day`."""
    if day.day <= 15:
        return day.replace(day=1), day.replace(day=15)
    last = calendar.monthrange(day.year, day.month)[1]
    return day.replace(day=16), day.replace(day=last)


def closes_month(end: date) -> bool:
    """A payroll that ends on the month's last day: the one that pays commissions."""
    return end.day == calendar.monthrange(end.year, end.month)[1]


# Kinds that wait for the payroll that closes the month.
MONTH_END_KINDS = {"comision"}


def monthly_share(monthly: float, start: date, end: date, hired: Optional[date] = None) -> float:
    """What a monthly salary pays for start..end (both included): half per full quincena, and the
    share of its days for a partial one. Days before `hired` are not paid."""
    if hired and hired > start:
        start = hired
    if not monthly or end < start:
        return 0.0
    total = 0.0
    day = start
    while day <= end:
        first, last = quincena_of(day)
        covered_until = min(end, last)
        total += (monthly / 2) * ((covered_until - day).days + 1) / ((last - first).days + 1)
        day = covered_until + timedelta(days=1)
    return total


def overtime_rate(person) -> float:
    """Hourly base for overtime (paid at 1.5x): the person's hourly rate, or what their daily
    rate or monthly salary gives when they have none."""
    if person.hourly_rate:
        return person.hourly_rate
    if person.pay_type == "dia" and person.daily_rate:
        return person.daily_rate / 8
    if person.pay_type == "mensual" and person.monthly_salary:
        return person.monthly_salary / HOURS_PER_MONTH
    return 0.0


# Lines on a payroll entry (Fase 4): (label, what it touches).
#   "salario": added to the gross, so it carries CCSS and counts for the aguinaldo;
#   "suma": added to the net (viáticos are not salary); "resta": taken from the net.
LINE_KINDS = {
    "bono": ("Bono", "salario"),
    "comision": ("Comisión", "salario"),
    "ajuste": ("Ajuste de salario", "salario"),
    "viatico": ("Viáticos", "suma"),
    "deduccion": ("Deducción", "resta"),
    "adelanto": ("Adelanto", "resta"),
}
# Corrections can go either way (a negative ajuste takes back salary paid of more).
SIGNED_KINDS = ("ajuste", "comision")
CCSS_RATE = 0.0917


def valid_line(kind: str, amount) -> Optional[str]:
    """Why a line can't be saved, or None."""
    if kind not in LINE_KINDS:
        return "Tipo de línea no válido"
    if amount is None or amount == 0:
        return "El monto no puede ser 0"
    if amount < 0 and kind not in SIGNED_KINDS:
        return "Solo un ajuste o una comisión pueden ser negativos"
    return None


def line_sums(lines) -> dict:
    """What the lines add to the gross ("salario") and to the net ("suma" − "resta")."""
    sums = {"salario": 0.0, "suma": 0.0, "resta": 0.0}
    for line in lines:
        sums[LINE_KINDS.get(line.kind, ("", "suma"))[1]] += line.amount or 0.0
    return sums


def recompute(entry) -> None:
    """Gross = base salary + salary lines; CCSS on the gross (rounded to hundreds) when it applies;
    net = gross − CCSS + viáticos − deducciones and adelantos."""
    if entry.base_salary is None:
        entry.base_salary = entry.gross_salary or 0.0
    sums = line_sums(entry.lines)
    gross = (entry.base_salary or 0.0) + sums["salario"]
    charges = round(max(gross, 0.0) * CCSS_RATE / 100) * 100 if entry.apply_deductions else 0.0
    entry.gross_salary = gross
    entry.social_charges = charges
    entry.net_salary = gross - charges + sums["suma"] - sums["resta"]


def _plain(text: str) -> str:
    """Lowercase without accents, so "jose" finds "José"."""
    import unicodedata
    return "".join(c for c in unicodedata.normalize("NFD", (text or "").lower()) if unicodedata.category(c) != "Mn")


def filter_people(people, q: Optional[str] = None, ver: Optional[str] = None) -> list:
    """Pagos and Liquidaciones lists: by name, and only the active people unless ver == "todos"."""
    text = _plain((q or "").strip())
    return [p for p in people
            if (ver == "todos" or p.status == "active")
            and (not text or text in _plain(p.full_name or p.username) or text in _plain(p.username))]
