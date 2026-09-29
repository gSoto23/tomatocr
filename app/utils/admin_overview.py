"""What each role's Dashboard shows first. The admin: today in the field, what needs attention
and the money that matters (what is owed, overdue and still to invoice); the supervisor, the
worker, the client and sales get the parts that concern them."""
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


# Most important first. urgente: money or people waiting; importante: affects the work
# soon; revisar: worth fixing, no hurry.
LEVELS = ("urgente", "importante", "revisar")
LEVEL_LABELS = {"urgente": "Urgente", "importante": "Importante", "revisar": "Para revisar"}


@dataclass
class Alert:
    key: str      # stable id, for "ya lo vi"
    level: str    # one of LEVELS
    title: str
    detail: str
    url: str
    action: str
    # What the alert is made of (invoice ids, days...): a mark hides it until a new item appears.
    items: List[str] = field(default_factory=list)
    # Extra direct links, e.g. one "Registrar bitácora" per missing day.
    links: List[tuple] = field(default_factory=list)


def by_importance(alerts: List[Alert]) -> List[Alert]:
    return sorted(alerts, key=lambda a: LEVELS.index(a.level))


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


def field_today(db: Session, today: date):
    """Each project with people today, who they are and whether its report is in."""
    todays = db.query(ProjectSchedule).filter(ProjectSchedule.date == today).all()
    reported_today = {pid for (pid,) in db.query(DailyLog.project_id).filter(DailyLog.date == today)}
    by_project: Dict[int, List[ProjectSchedule]] = {}
    for s in todays:
        if s.project:
            by_project.setdefault(s.project_id, []).append(s)
    days = sorted((FieldDay(rows[0].project, names(r.user for r in rows), pid in reported_today)
                   for pid, rows in by_project.items()), key=lambda d: d.project.name.lower())
    return days, len({s.user_id for s in todays})


def missing_reports(db: Session, today: date, user_id: Optional[int] = None) -> List[tuple]:
    """(project_id, day) of the last days that had people assigned but no report of that project.
    With user_id, only the days that person was assigned."""
    since = today - timedelta(days=MISSING_REPORT_DAYS)
    query = db.query(ProjectSchedule.project_id, ProjectSchedule.date).filter(
        ProjectSchedule.date >= since, ProjectSchedule.date < today)
    if user_id:
        query = query.filter(ProjectSchedule.user_id == user_id)
    reported = {(pid, d) for pid, d in db.query(DailyLog.project_id, DailyLog.date).filter(
        DailyLog.date >= since, DailyLog.date < today)}
    return sorted({(pid, d) for pid, d in query.distinct()} - reported, key=lambda x: x[1], reverse=True)


def missing_alert(db: Session, missing: List[tuple]) -> Alert:
    projects = {p.id: p.name for p in db.query(Project).filter(Project.id.in_({pid for pid, _ in missing}))}
    listed = ", ".join(f"{projects.get(pid, '?')} ({d:%d/%m})" for pid, d in missing[:3])
    more = f" y {len(missing) - 3} más" if len(missing) > 3 else ""
    return Alert("sin_bitacora", "importante", n(len(missing), "día trabajado sin bitácora", "días trabajados sin bitácora"),
                 f"Últimos {MISSING_REPORT_DAYS} días: {listed}{more}.", "/logs/", "Ver bitácora",
                 items=[f"{pid}:{d.isoformat()}" for pid, d in missing])


def unconfirmed_alert(db: Session, today: date, exclude_user_id: Optional[int] = None) -> Optional[Alert]:
    query = db.query(ProjectSchedule).filter(ProjectSchedule.date < today,
                                             ProjectSchedule.is_confirmed == False)  # noqa: E712
    if exclude_user_id:
        query = query.filter(ProjectSchedule.user_id != exclude_user_id)
    rows = query.order_by(ProjectSchedule.date).all()
    if not rows:
        return None
    return Alert("horas_sin_confirmar", "urgente", n(len(rows), "jornada con horas sin confirmar", "jornadas con horas sin confirmar"),
                 f"Desde el {rows[0].date:%d/%m/%Y}. Sin confirmar no entran en la planilla.",
                 "/calendar", "Confirmar en el Calendario", items=[str(r.id) for r in rows])


def supervisor_overview(db: Session, today: date, user: User) -> Overview:
    """The supervisor organizes the whole team: today in the field and what's pending."""
    ov = Overview(today=today)
    ov.in_field, ov.counts["people_today"] = field_today(db, today)
    alert = unconfirmed_alert(db, today, exclude_user_id=user.id)
    if alert:
        ov.alerts.append(alert)
    missing = missing_reports(db, today)
    if missing:
        ov.alerts.append(missing_alert(db, missing))
    ov.alerts = by_importance(ov.alerts)
    return ov


def worker_missing(db: Session, today: date, user: User) -> List[dict]:
    """The worker's own assigned days without a report, to register them (up to 7 days back)."""
    missing = missing_reports(db, today, user_id=user.id)
    projects = {p.id: p.name for p in db.query(Project).filter(Project.id.in_({pid for pid, _ in missing}))}
    return [{"project_id": pid, "project": projects.get(pid, "?"), "date": d} for pid, d in missing]


def worker_alerts(db: Session, today: date, user: User) -> List[Alert]:
    """The worker's own days without a report, each with its link to register it."""
    missing = worker_missing(db, today, user)
    if not missing:
        return []
    return [Alert("mis_dias_sin_bitacora", "importante",
                  "Te quedó 1 día sin bitácora" if len(missing) == 1 else f"Te quedaron {len(missing)} días sin bitácora",
                  f"Días que tenías asignados en los últimos {MISSING_REPORT_DAYS} y que nadie reportó. Registralos antes de que pase la semana.",
                  "/logs/new", "Registrar bitácora",
                  items=[f"{m['project_id']}:{m['date'].isoformat()}" for m in missing],
                  links=[(f"{m['date']:%d/%m} · {m['project']}", f"/logs/new?project_id={m['project_id']}&date={m['date'].isoformat()}")
                         for m in missing])]


def sales_alerts(next_steps: Dict) -> List[Alert]:
    late = next_steps.get("vencidos", [])
    if not late:
        return []
    return [Alert("mis_pasos_atrasados", "urgente", n(len(late), "próximo paso atrasado", "próximos pasos atrasados"),
                  "Oportunidades con la fecha del próximo paso ya pasada: atendelas primero.", "/clientes", "Ver Clientes",
                  items=[str(o.id) for o in late],
                  links=[(f"{o.account.name} · {o.next_step_date:%d/%m}", f"/clientes/oportunidades/{o.id}") for o in late[:5]])]


def client_projects(db: Session, today: date, projects) -> List[dict]:
    """Per project the client sees: last visit, next scheduled day (date only) and reports this month."""
    rows = []
    month_start = today.replace(day=1)
    for p in projects:
        last = db.query(func.max(DailyLog.date)).filter(DailyLog.project_id == p.id).scalar()
        upcoming = db.query(func.min(ProjectSchedule.date)).filter(ProjectSchedule.project_id == p.id,
                                                                   ProjectSchedule.date >= today).scalar()
        month = db.query(func.count(DailyLog.id)).filter(DailyLog.project_id == p.id,
                                                          DailyLog.date >= month_start).scalar()
        rows.append({"project": p, "last_visit": last, "next_visit": upcoming, "reports_month": month or 0})
    return sorted(rows, key=lambda r: (not r["project"].is_active, r["project"].name.lower()))


def admin_overview(db: Session, today: date, next_steps: Optional[Dict] = None,
                   expiring: Optional[List[Dict]] = None) -> Overview:
    ov = Overview(today=today)

    # --- Today in the field: each project with people today and whether its report is in.
    ov.in_field, ov.counts["people_today"] = field_today(db, today)

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
        ov.alerts.append(Alert("facturas_vencidas", "urgente", n(len(overdue), "factura vencida", "facturas vencidas"),
                               f"₡{ov.money['overdue']:,.2f} sin cobrar; la más vieja venció el {oldest:%d/%m/%Y}.",
                               "/dashboard?invoice_status=vencida", "Ver facturas", items=[str(i.id) for i in overdue]))

    missing = missing_reports(db, today)
    if missing:
        ov.alerts.append(missing_alert(db, missing))
    ov.counts["missing_reports"] = len(missing)

    alert = unconfirmed_alert(db, today)
    if alert:
        ov.alerts.append(alert)

    drafts = db.query(PayrollPeriod).filter(PayrollPeriod.status == "draft").order_by(PayrollPeriod.start_date).all()
    if drafts:
        first = drafts[0]
        ov.alerts.append(Alert("planillas_borrador", "importante", n(len(drafts), "planilla en borrador", "planillas en borrador"),
                               f"La primera es del {first.start_date:%d/%m} al {first.end_date:%d/%m/%Y}.",
                               f"/payroll/detail/{first.id}", "Revisar", items=[str(d.id) for d in drafts]))

    late = (next_steps or {}).get("vencidos", [])
    if late:
        ov.alerts.append(Alert("pasos_atrasados", "importante", n(len(late), "próximo paso atrasado en Clientes", "próximos pasos atrasados en Clientes"),
                               "Oportunidades con la fecha del próximo paso ya pasada.", "/clientes", "Ver Clientes",
                               items=[str(o.id) for o in late]))

    pending_renewals = [row for row in (expiring or []) if not row["renewal"]]
    if pending_renewals:
        urgent = [row for row in pending_renewals if row["urgent"]]
        first = pending_renewals[0]
        ov.alerts.append(Alert("contratos_por_vencer", "importante" if urgent else "revisar",
                               n(len(pending_renewals), "contrato por vencer sin renovación", "contratos por vencer sin renovación"),
                               f"El primero, {first['project'].name}, vence el {first['end_date']:%d/%m/%Y} ({first['days_left']} días).",
                               "/clientes", "Crear renovación", items=[str(row["project"].id) for row in pending_renewals]))

    without_email = db.query(User.id).filter((User.email.is_(None)) | (User.email == ""),
                                             User.is_active == True).all()  # noqa: E712
    if without_email:
        ov.alerts.append(Alert("sin_correo", "revisar", n(len(without_email), "persona activa sin correo", "personas activas sin correo"),
                               "No pueden recuperar su contraseña.", "/users/", "Agregar correos",
                               items=[str(uid) for (uid,) in without_email]))
    ov.alerts = by_importance(ov.alerts)
    return ov
