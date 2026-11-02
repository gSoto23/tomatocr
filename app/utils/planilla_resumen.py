"""One person's numbers in a payroll, and the payroll's totals, the same for the detail screen,
the payslip (comprobante) and the Excel export (docs/PLAN_PLANILLA_CALENDARIO.md, Fase 6)."""
import io
from datetime import date
from typing import Iterable, List, Optional

from app.utils.planilla import LINE_KINDS, PAY_TYPES, line_sums

# Employer charges on the gross, as the payroll detail always showed them.
EMPLOYER_CHARGES = 0.2667
PROVISIONS = 0.18
ATTENDANCE_NOTE = {"tarde": "Llegó tarde", "no_llego": "No llegó"}
MONTHS = ("ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "set", "oct", "nov", "dic")


def entry_rate(entry) -> float:
    """The rate frozen when the payroll was generated (older entries: the person's rate)."""
    if entry.hourly_rate is not None:
        return entry.hourly_rate
    return (entry.user.hourly_rate if entry.user else 0.0) or 0.0


def overtime_amount(overtime_hours: float, rate: float) -> float:
    """Overtime at 1.5x, rounded to hundreds like the gross salary."""
    return round(((overtime_hours or 0.0) * rate * 1.5) / 100) * 100


def period_label(period) -> str:
    """"16–31 oct 2026": how people name a quincena."""
    start, end = period.start_date, period.end_date
    if start.year == end.year and start.month == end.month:
        return f"{start.day}–{end.day} {MONTHS[end.month - 1]} {end.year}"
    if start.year == end.year:
        return f"{start.day} {MONTHS[start.month - 1]} – {end.day} {MONTHS[end.month - 1]} {end.year}"
    return f"{start:%d/%m/%Y} – {end:%d/%m/%Y}"


def entry_view(entry, paid_users: Optional[set] = None) -> dict:
    """Everything one row, one person panel or one payslip shows."""
    person = entry.user
    rate = entry_rate(entry)
    gross = entry.gross_salary or 0.0
    base = entry.base_salary if entry.base_salary is not None else gross
    extra = overtime_amount(entry.overtime_hours, rate)
    sums = line_sums(entry.lines)
    pay_type = entry.pay_type or "hora"
    if pay_type == "mensual":
        how = "Mensual (media quincena del salario)"
    elif pay_type == "dia":
        days = int(entry.days_worked or 0)
        how = f"Por día · {days} {'día' if days == 1 else 'días'}"
    else:
        how = f"Por hora · ₡{rate:,.0f}/h"
    lines = []
    for line in entry.lines:
        label, effect = LINE_KINDS.get(line.kind, (line.kind, "suma"))
        lines.append({"id": line.id, "kind": line.kind, "label": label, "effect": effect,
                      "description": line.description, "amount": line.amount,
                      "signed": -line.amount if effect == "resta" else line.amount,
                      "from_adjustment": line.adjustment_id is not None})
    days = [{**d, "note": ATTENDANCE_NOTE.get(d.get("attendance"), "")} for d in (entry.details or [])]
    return {
        "id": entry.id,
        "user": person,
        "name": (person.full_name or person.username) if person else "?",
        "pay_type": pay_type,
        "pay_type_label": PAY_TYPES.get(pay_type, pay_type),
        "how": how,
        "rate": rate,
        "hours": entry.total_hours or 0.0,
        "overtime_hours": entry.overtime_hours or 0.0,
        "days_worked": entry.days_worked,
        "regular": base - extra,
        "overtime": extra,
        "base": base,
        "salary_lines": sums["salario"],
        "gross": gross,
        "ccss": entry.social_charges or 0.0,
        "apply_deductions": entry.apply_deductions,
        "viaticos": sums["suma"],
        "minus": sums["resta"],
        "net_lines": sums["suma"] - sums["resta"],
        "net": entry.net_salary or 0.0,
        "employer": gross * EMPLOYER_CHARGES,
        "provisions": gross * PROVISIONS,
        "lines": lines,
        "days": days,
        "payment_method": (person.payment_method if person else None) or "Sin método",
        "account": person.account_number if person and person.payment_method in ("Transferencia", "Sinpe") else None,
        "paid": paid_users is not None and entry.user_id in paid_users,
    }


def totals_of(rows: Iterable[dict]) -> dict:
    rows = list(rows)
    keys = ("hours", "overtime_hours", "regular", "overtime", "base", "salary_lines", "gross", "ccss", "viaticos",
            "minus", "net_lines", "net", "employer", "provisions")
    totals = {key: sum(r[key] for r in rows) for key in keys}
    totals["people"] = len(rows)
    totals["company_cost"] = totals["gross"] + totals["employer"] + totals["provisions"] + totals["viaticos"]
    totals["paid"] = sum(1 for r in rows if r["paid"])
    return totals


# ---- Excel ------------------------------------------------------------------------------------------

def payroll_workbook(period, rows: List[dict], totals: dict, company: str) -> bytes:
    """Resumen (one row per person, with the employer's cost), Líneas and Días."""
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter

    money = '"₡"#,##0.00'
    bold, head_fill = Font(bold=True), PatternFill("solid", fgColor="E5E7EB")
    book = Workbook()

    def sheet(ws, title_cells, header, data, money_cols=(), widths=None):
        for row in title_cells:
            ws.append(row)
        ws.append([])
        ws.append(header)
        head_row = ws.max_row
        for cell in ws[head_row]:
            cell.font, cell.fill = bold, head_fill
            cell.alignment = Alignment(wrap_text=True, vertical="center")
        for values in data:
            ws.append(values)
        for col in money_cols:
            for r in range(head_row + 1, ws.max_row + 1):
                ws.cell(row=r, column=col).number_format = money
        for i, width in enumerate(widths or [], 1):
            ws.column_dimensions[get_column_letter(i)].width = width
        ws.freeze_panes = ws.cell(row=head_row + 1, column=2)

    title = [[f"Planilla #{period.id} · {period_label(period)}"], [company],
             [f"Estado: {'Aprobada' if period.status == 'final' else 'Borrador'}"]]
    summary = book.active
    summary.title = "Resumen"
    header = ["Persona", "Forma de pago", "Horas", "Horas extra", "Salario", "Extras", "Bonos y ajustes", "Bruto",
              "CCSS trabajador", "Viáticos", "Deducciones y adelantos", "Neto a pagar", "Método", "Cuenta",
              "Cargas patronales (26,67 %)", "Previsiones (18 %)"]
    data = [[r["name"], r["how"], r["hours"], r["overtime_hours"], r["regular"], r["overtime"], r["salary_lines"],
             r["gross"], r["ccss"], r["viaticos"], r["minus"], r["net"], r["payment_method"], r["account"] or "",
             r["employer"], r["provisions"]] for r in rows]
    data.append(["Total", f"{totals['people']} personas", totals["hours"], totals["overtime_hours"], totals["regular"],
                 totals["overtime"], totals["salary_lines"], totals["gross"], totals["ccss"], totals["viaticos"],
                 totals["minus"], totals["net"], "", "", totals["employer"], totals["provisions"]])
    sheet(summary, title, header, data, money_cols=(5, 6, 7, 8, 9, 10, 11, 12, 15, 16),
          widths=[26, 30, 8, 8, 14, 12, 14, 14, 14, 12, 16, 15, 13, 16, 16, 14])
    for cell in summary[summary.max_row]:
        cell.font = bold
    summary.append([])
    summary.append(["Costo total para la empresa", None, None, None, None, None, None, None, None, None, None,
                    totals["company_cost"]])
    summary.cell(row=summary.max_row, column=1).font = bold
    summary.cell(row=summary.max_row, column=12).number_format = money

    lines_ws = book.create_sheet("Líneas")
    sheet(lines_ws, title, ["Persona", "Tipo", "Detalle", "Monto"],
          [[r["name"], line["label"], line["description"], line["signed"]] for r in rows for line in r["lines"]],
          money_cols=(4,), widths=[26, 18, 50, 14])

    days_ws = book.create_sheet("Días")
    sheet(days_ws, title, ["Persona", "Fecha", "Proyecto", "Horas", "Horas extra", "Asistencia"],
          [[r["name"], date.fromisoformat(d["date"]) if d.get("date") else "", d.get("project", ""), d.get("hours"),
            d.get("overtime") or 0, d["note"]] for r in rows for d in r["days"]],
          widths=[26, 12, 30, 8, 10, 14])
    for row in days_ws.iter_rows(min_row=6, min_col=2, max_col=2):
        for cell in row:
            cell.number_format = "DD/MM/YYYY"

    out = io.BytesIO()
    book.save(out)
    return out.getvalue()
