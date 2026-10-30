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
