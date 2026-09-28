"""The company's legal data, for printed documents (liquidation letter, payroll report)."""
from datetime import date

COMPANY = {
    "name": "TOMATO COSTA RICA ANY S.R.L.",
    "tax_id": "3-102-876296",
    "phone": "7080-8613",
    "web": "www.tomatocr.com",
    "city": "Alajuela",
    "address": "Alajuela, Alajuela, barrio San José, Condominio Botánica, casa 59A",
}

MONTHS = ("enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre",
          "noviembre", "diciembre")


def long_date(day: date) -> str:
    """27 de septiembre de 2026 (not dependent on the server locale)."""
    return f"{day.day} de {MONTHS[day.month - 1]} de {day.year}"
