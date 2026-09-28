"""What the admin's Dashboard shows first: today in the field, what needs attention and
the money that matters (what is owed, overdue and still to invoice)."""
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Dict, List, Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.db.models.finance import Invoice, InvoiceStatus, ProjectBudget
from app.db.models.log import DailyLog
from app.db.models.payroll import PayrollPeriod
from app.db.models.project import Project
from app.db.models.schedule import ProjectSchedule
from app.db.models.user import User

OPEN_INVOICES = (InvoiceStatus.PENDING, InvoiceStatus.PARTIAL, InvoiceStatus.OVERDUE)
MISSING_REPORT_DAYS = 7  # how far back a day without a report is still flagged


@dataclass
class FieldDay:
    project: Project
    people: List[str]
    reported: bool


@dataclass
class Alert:
    level: str   # "red" (money or people waiting) or "amber"
    title: str
    detail: str
    url: str
    action: str


@dataclass
class Overview:
    today: date
    in_field: List[FieldDay] = field(default_factory=list)
    alerts: List[Alert] = field(default_factory=list)
    money: Dict[str, float] = field(default_factory=dict)
    counts: Dict[str, int] = field(default_factory=dict)


def n(count: int, one: str, many: str) -> str:
    """1 factura vencida / 3 facturas vencidas."""
    return f"{count} {one if count == 1 else many}"


def owed(invoice: Invoice) -> float:
    paid = (invoice.payment.amount or 0.0) + (invoice.payment.retention_amount or 0.0) if invoice.payment else 0.0
    return max(0.0, (invoice.amount or 0.0) - paid)


def names(people) -> List[str]:
    return sorted({(u.full_name or u.username) for u in people if u})


def admin_overview(db: Session, today: date, next_steps: Optional[Dict] = None) -> Overview:
    ov = Overview(today=today)

    # --- Today in the field: each project with people today and whether its report is in.
    todays = db.query(ProjectSchedule).filter(ProjectSchedule.date == today).all()
    reported_today = {pid for (pid,) in db.query(DailyLog.project_id).filter(DailyLog.date == today)}
    by_project: Dict[int, List[ProjectSchedule]] = {}
    for s in todays:
        if s.project:
            by_project.setdefault(s.project_id, []).append(s)
    ov.in_field = sorted((FieldDay(rows[0].project, names(r.user for r in rows), pid in reported_today)
                       for pid, rows in by_project.items()), key=lambda d: d.project.name.lower())
    ov.counts["people_today"] = len({s.user_id for s in todays})

    # --- Money.
    open_invoices = db.query(Invoice).join(ProjectBudget).join(Project).filter(
        Project.is_active == True, Invoice.status.in_(OPEN_INVOICES)).all()  # noqa: E712
    overdue = [i for i in open_invoices if i.status == InvoiceStatus.OVERDUE]
    ov.money["receivable"] = sum(owed(i) for i in open_invoices)
    ov.money["overdue"] = sum(owed(i) for i in overdue)
    ov.counts["overdue"] = len(overdue)
    month_start = today.replace(day=1)
    ov.money["invoiced_month"] = db.query(func.coalesce(func.sum(Invoice.amount), 0.0)).filter(
        Invoice.issue_date >= month_start, Invoice.issue_date <= today).scalar() or 0.0
    adjudicated = 0.0
    invoiced = 0.0
    for budget in db.query(ProjectBudget).join(Project).filter(Project.is_active == True):  # noqa: E712
        adjudicated += sum(l.subtotal * (1 + (l.tax_percentage or 0) / 100.0) for l in budget.lines)
        if budget.is_prorrogable and budget.active_prorogue:
            adjudicated += budget.prorrogable_amount or 0.0
        invoiced += sum(i.amount or 0.0 for i in budget.invoices)
    ov.money["to_invoice"] = max(0.0, adjudicated - invoiced)

    # --- What needs attention, most urgent first.
    if overdue:
        oldest = min(i.due_date for i in overdue)
        ov.alerts.append(Alert("red", n(len(overdue), "factura vencida", "facturas vencidas"),
                               f"₡{ov.money['overdue']:,.2f} sin cobrar; la más vieja venció el {oldest:%d/%m/%Y}.",
                               "/dashboard?invoice_status=vencida", "Ver facturas"))

    since = today - timedelta(days=MISSING_REPORT_DAYS)
    past = db.query(ProjectSchedule.project_id, ProjectSchedule.date).filter(
        ProjectSchedule.date >= since, ProjectSchedule.date < today).distinct().all()
    reported = {(pid, d) for pid, d in db.query(DailyLog.project_id, DailyLog.date).filter(
        DailyLog.date >= since, DailyLog.date < today)}
    missing = sorted({(pid, d) for pid, d in past} - reported, key=lambda x: x[1], reverse=True)
    if missing:
        projects = {p.id: p.name for p in db.query(Project).filter(Project.id.in_({pid for pid, _ in missing}))}
        listed = ", ".join(f"{projects.get(pid, '?')} ({d:%d/%m})" for pid, d in missing[:3])
        more = f" y {len(missing) - 3} más" if len(missing) > 3 else ""
        ov.alerts.append(Alert("amber", n(len(missing), "día trabajado sin bitácora", "días trabajados sin bitácora"),
                               f"Últimos {MISSING_REPORT_DAYS} días: {listed}{more}.", "/logs/", "Ver bitácora"))
    ov.counts["missing_reports"] = len(missing)

    unconfirmed = db.query(ProjectSchedule).filter(ProjectSchedule.date < today,
                                                   ProjectSchedule.is_confirmed == False)  # noqa: E712
    pending = unconfirmed.count()
    if pending:
        oldest = unconfirmed.order_by(ProjectSchedule.date).first().date
        ov.alerts.append(Alert("amber", n(pending, "jornada con horas sin confirmar", "jornadas con horas sin confirmar"),
                               f"Desde el {oldest:%d/%m/%Y}. Sin confirmar no entran en la planilla.",
                               "/calendar", "Confirmar en el Calendario"))
    ov.counts["unconfirmed"] = pending

    drafts = db.query(PayrollPeriod).filter(PayrollPeriod.status == "draft").order_by(PayrollPeriod.start_date).all()
    if drafts:
        first = drafts[0]
        ov.alerts.append(Alert("amber", n(len(drafts), "planilla en borrador", "planillas en borrador"),
                               f"La primera es del {first.start_date:%d/%m} al {first.end_date:%d/%m/%Y}.",
                               f"/payroll/detail/{first.id}", "Revisar"))

    late_steps = len((next_steps or {}).get("vencidos", []))
    if late_steps:
        ov.alerts.append(Alert("amber", n(late_steps, "próximo paso atrasado en Clientes", "próximos pasos atrasados en Clientes"),
                               "Oportunidades con la fecha del próximo paso ya pasada.", "/clientes", "Ver Clientes"))

    without_email = db.query(User).filter((User.email.is_(None)) | (User.email == ""),
                                          User.is_active == True).count()  # noqa: E712
    if without_email:
        ov.alerts.append(Alert("amber", n(without_email, "persona activa sin correo", "personas activas sin correo"),
                               "No pueden recuperar su contraseña.", "/users/", "Agregar correos"))
    return ov
