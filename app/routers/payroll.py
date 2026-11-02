from typing import List, Optional
from datetime import date, datetime
from fastapi import APIRouter, Depends, HTTPException, Body, Form, Request
from fastapi.responses import JSONResponse, HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.routers import deps
from app.core.roles import ADMIN, SUPERVISOR, VENTAS, WORKER
from app.db.models.user import User
from app.db.models.schedule import ProjectSchedule
from app.db.models.commission import Commission
from app.db.models.payroll import PayrollAdjustment, PayrollEntry, PayrollLine, PayrollPeriod
import pydantic
from app.db.models.project import Project
from app.utils.activity import log_activity
from app.utils.comisiones import KINDS as COMMISSION_KINDS, STATUS_LABELS, cancel, general_rules, \
    rules_for, set_general_rules, status_of
from app.utils.planilla import LINE_KINDS, monthly_share, overtime_rate, recompute, valid_line
from app.utils.planilla_resumen import entry_view, payroll_workbook, period_label, totals_of
from app.utils.timecr import today_cr
from app.core.templates import templates

router = APIRouter(
    prefix="/payroll",
    tags=["payroll"],
    dependencies=[Depends(deps.require_roles(ADMIN, SUPERVISOR, WORKER, VENTAS))]
)

# People in the payroll. Everyone but the admin sees only their own entries and payments.
PAYROLL_PEOPLE = (WORKER, SUPERVISOR, VENTAS)
COMPANY = "TOMATO COSTA RICA ANY S.R.L. · Cédula jurídica 3-102-876296"

def vacation_balance(user: User) -> dict:
    """1 day per month worked since the start date, minus the days already taken."""
    earned = 0.0
    if user.start_date:
        days = (today_cr() - user.start_date).days
        earned = max(0.0, days / 30.44)
    taken = user.vacation_days_taken or 0.0
    return {"earned": round(earned, 2), "taken": round(taken, 2), "vacation_days": round(max(0.0, earned - taken), 2)}


def pending_adjustments(db: Session):
    """Adjustments that no payroll line applies yet, oldest first."""
    applied = db.query(PayrollLine.adjustment_id).filter(PayrollLine.adjustment_id.isnot(None))
    return db.query(PayrollAdjustment).filter(~PayrollAdjustment.id.in_(applied)).order_by(PayrollAdjustment.id)


def payment_status(db: Session, period: PayrollPeriod) -> dict:
    """An approved payroll is "pagada" once everyone with something to receive has a payment
    registered against it (Historial de Pagos → Planilla que paga), or once the admin marked it as
    paid outside the system."""
    from app.db.models.payment import PayrollPayment
    owed = {e.user_id for e in period.entries if (e.net_salary or 0) > 0}
    paid = {uid for (uid,) in db.query(PayrollPayment.user_id).filter(PayrollPayment.payroll_period_id == period.id)}
    done = len(owed & paid)
    outside = period.paid_outside_at is not None
    return {"owed": len(owed), "paid": done, "outside": outside,
            "complete": period.status == "final" and (done == len(owed) or outside)}


def set_confirmed_hours(schedule: ProjectSchedule, hours: float, overtime: float):
    """Aprobar Horas: a day marked "No llegó" in the calendar that gets hours here did happen."""
    schedule.hours_worked = hours
    schedule.overtime_hours = overtime
    schedule.is_confirmed = True
    if schedule.attendance == "no_llego" and (hours or overtime):
        schedule.attendance = "asistio"


def period_rows(db: Session, period: PayrollPeriod, user: Optional[User] = None) -> list:
    """The payroll's people as entry_view() rows (only the user's own when given)."""
    from app.db.models.payment import PayrollPayment
    paid = {uid for (uid,) in db.query(PayrollPayment.user_id).filter(PayrollPayment.payroll_period_id == period.id)}
    entries = sorted(period.entries, key=lambda e: ((e.user.full_name or e.user.username) if e.user else "").lower())
    return [entry_view(e, paid) for e in entries if user is None or e.user_id == user.id]


def visible_period(db: Session, period_id: int, user: User) -> PayrollPeriod:
    """A payroll the user may open: the admin any; everyone else an approved one they are in
    (a draft can still change, so it isn't shown to them)."""
    period = db.get(PayrollPeriod, period_id)
    if not period:
        raise HTTPException(status_code=404, detail="Payroll period not found")
    if user.role != ADMIN:
        if period.status != "final" or not any(e.user_id == user.id for e in period.entries):
            raise HTTPException(status_code=404, detail="Esta planilla no está disponible")
    return period


@router.get("/", response_class=HTMLResponse)
def payroll_dashboard(
    request: Request,
    db: Session = Depends(deps.get_db),
    user: User = Depends(deps.get_current_user)
):
    if user.role not in (ADMIN, *PAYROLL_PEOPLE):
         raise HTTPException(status_code=403, detail="Not authorized")

    query = db.query(PayrollPeriod).order_by(PayrollPeriod.start_date.desc())
    if user.role in PAYROLL_PEOPLE:
        # Their approved payrolls only: a draft can still change.
        query = query.join(PayrollEntry).filter(PayrollEntry.user_id == user.id, PayrollPeriod.status == "final")
    periods = query.all()

    worker_stats, mine = {}, {}
    if user.role in PAYROLL_PEOPLE:
        worker_stats = vacation_balance(user)
        mine = {e.payroll_period_id: e.net_salary for e in db.query(PayrollEntry).filter(PayrollEntry.user_id == user.id)}

    # Admin: each payroll's size and payments, what to do next, and the adjustments waiting.
    summaries, pending, todo = {}, [], {}
    if user.role == ADMIN:
        for p in periods:
            status = payment_status(db, p)
            summaries[p.id] = {"people": len(p.entries), "net": sum(e.net_salary or 0 for e in p.entries), **status}
        pending = pending_adjustments(db).all()
        todo = {
            "hours": db.query(ProjectSchedule).filter(ProjectSchedule.is_confirmed == False,  # noqa: E712
                                                      ProjectSchedule.date <= today_cr()).count(),
            "drafts": [p for p in periods if p.status == "draft"],
            "unpaid": [p for p in periods if p.status == "final" and not summaries[p.id]["complete"]
                       and summaries[p.id]["paid"] < summaries[p.id]["owed"]][:3],
        }
    # Commission adjustments are cancelled from Comisiones, not deleted here.
    from_commissions = {i for row in db.query(Commission.adjustment_id, Commission.reversal_adjustment_id)
                        for i in row if i} if pending else set()

    return templates.TemplateResponse("payroll/index.html", {
        "from_commissions": from_commissions,
        "request": request,
        "user": user,
        "periods": periods,
        "labels": {p.id: period_label(p) for p in periods},
        "worker_stats": worker_stats,
        "mine": mine,
        "summaries": summaries,
        "todo": todo,
        "pending": pending,
        "line_kinds": LINE_KINDS,
    })

@router.get("/approval", response_class=HTMLResponse)
def approval_view(
    request: Request,
    db: Session = Depends(deps.get_db),
    user: User = Depends(deps.get_current_user)
):
    if user.role not in [ADMIN, SUPERVISOR]:
         raise HTTPException(status_code=403, detail="Not authorized")
    # How many past days wait for confirmation, per project (the cards show it).
    from sqlalchemy import func
    pending = dict(db.query(ProjectSchedule.project_id, func.count(ProjectSchedule.id)).filter(
        ProjectSchedule.is_confirmed == False, ProjectSchedule.date <= today_cr())  # noqa: E712
        .group_by(ProjectSchedule.project_id).all())
    return templates.TemplateResponse("payroll/approval.html", {
        "request": request,
        "user": user,
        "pending_by_project": pending,
    })


@router.get("/detail/{period_id}", response_class=HTMLResponse)
def payroll_detail(
    period_id: int,
    request: Request,
    db: Session = Depends(deps.get_db),
    user: User = Depends(deps.get_current_user)
):
    if user.role not in (ADMIN, *PAYROLL_PEOPLE):
         raise HTTPException(status_code=403, detail="Not authorized")
    period = visible_period(db, period_id, user)
    # Everyone but the admin sees their own payslip.
    if user.role != ADMIN:
        return payslip_page(request, period, period_rows(db, period, user), single=True, embedded=True, user=user)

    rows = period_rows(db, period)
    return templates.TemplateResponse("payroll/detail.html", {
        "request": request,
        "user": user,
        "period": period,
        "label": period_label(period),
        "rows": rows,
        # The person panel's data (the User object stays out of the JSON).
        "people": {r["id"]: {**{k: v for k, v in r.items() if k != "user"}, "user_id": r["user"].id} for r in rows},
        "totals": totals_of(rows),
        "payments": payment_status(db, period),
        "line_kinds": LINE_KINDS,
        "methods": ("Sinpe", "Transferencia", "Efectivo"),
        "today": today_cr(),
    })


def payslip_page(request: Request, period: PayrollPeriod, rows: list, single: bool, embedded: bool = False,
                 user: Optional[User] = None):
    return templates.TemplateResponse("payroll/payslip.html", {
        "request": request, "user": user, "period": period, "label": period_label(period), "rows": rows,
        "single": single, "embedded": embedded, "today": today_cr(), "company": COMPANY,
    })


@router.get("/{period_id}/comprobante/{entry_id}", response_class=HTMLResponse)
def payslip(period_id: int, entry_id: int, request: Request, db: Session = Depends(deps.get_db),
            user: User = Depends(deps.get_current_user)):
    """One person's payslip, to print or save as PDF (the person or the admin)."""
    period = visible_period(db, period_id, user)
    rows = [r for r in period_rows(db, period) if r["id"] == entry_id]
    if not rows or (user.role != ADMIN and rows[0]["user"].id != user.id):
        raise HTTPException(status_code=404, detail="Comprobante no encontrado")
    return payslip_page(request, period, rows, single=True)


@router.get("/{period_id}/comprobantes", response_class=HTMLResponse,
            dependencies=[Depends(deps.require_roles(ADMIN))])
def payslips(period_id: int, request: Request, db: Session = Depends(deps.get_db),
             user: User = Depends(deps.get_current_user)):
    """Everyone's payslips, one per page, to print them all at once."""
    period = visible_period(db, period_id, user)
    return payslip_page(request, period, period_rows(db, period), single=False)


@router.get("/{period_id}/excel", dependencies=[Depends(deps.require_roles(ADMIN))])
def payroll_excel(period_id: int, db: Session = Depends(deps.get_db), user: User = Depends(deps.get_current_user)):
    from fastapi.responses import Response
    period = visible_period(db, period_id, user)
    rows = period_rows(db, period)
    content = payroll_workbook(period, rows, totals_of(rows), COMPANY)
    name = f"planilla-{period.id}-{period.start_date:%Y-%m-%d}.xlsx"
    return Response(content, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": f'attachment; filename="{name}"'})


@router.get("/report/{period_id}", response_class=HTMLResponse)
def payroll_report(
    period_id: int,
    request: Request,
    db: Session = Depends(deps.get_db),
    user: User = Depends(deps.get_current_user)
):
    """The payment list (who, how, how much) to print; a person gets their payslip instead."""
    if user.role not in (ADMIN, *PAYROLL_PEOPLE):
         raise HTTPException(status_code=403, detail="Not authorized")
    period = visible_period(db, period_id, user)
    if user.role != ADMIN:
        return payslip_page(request, period, period_rows(db, period, user), single=True)
    rows = period_rows(db, period)
    return templates.TemplateResponse("payroll/report.html", {
        "request": request,
        "period": period,
        "label": period_label(period),
        "rows": rows,
        "totals": totals_of(rows),
        "today": today_cr(),
        "company": COMPANY,
    })


class EntryPaymentIn(pydantic.BaseModel):
    date: date
    method: str
    reference: str = ""


@router.post("/entry/{entry_id}/pay", dependencies=[Depends(deps.require_roles(ADMIN))])
def pay_entry(entry_id: int, data: EntryPaymentIn, db: Session = Depends(deps.get_db),
              user: User = Depends(deps.get_current_user)):
    """Register a person's payment from the approved payroll: its net, linked to it."""
    from app.db.models.payment import PayrollPayment
    entry = db.get(PayrollEntry, entry_id)
    if not entry:
        raise HTTPException(status_code=404, detail="Entry not found")
    if entry.period.status != "final":
        raise HTTPException(status_code=400, detail="Primero aprobá la planilla.")
    if entry.period.paid_outside_at is not None:
        raise HTTPException(status_code=400, detail=(
            "La quincena está marcada como pagada fuera del sistema. Deshacé eso primero para registrar pagos."))
    if db.query(PayrollPayment).filter(PayrollPayment.payroll_period_id == entry.payroll_period_id,
                                       PayrollPayment.user_id == entry.user_id).first():
        raise HTTPException(status_code=400, detail="Esa persona ya tiene su pago registrado en esta planilla.")
    if data.method not in ("Sinpe", "Transferencia", "Efectivo"):
        raise HTTPException(status_code=400, detail="Elegí cómo se pagó")
    payment = PayrollPayment(user_id=entry.user_id, amount=entry.net_salary or 0.0, hours_paid=entry.total_hours or 0.0,
                             overtime_hours=entry.overtime_hours or 0.0, date=data.date, method=data.method,
                             reference=data.reference.strip()[:100] or None, payroll_period_id=entry.payroll_period_id,
                             notes=f"Planilla #{entry.payroll_period_id}", created_by_id=user.id)
    db.add(payment)
    db.commit()
    person = entry.user.full_name or entry.user.username
    log_activity(db, user, "CREATE", "PAYMENT", payment.id,
                 f"Pago de {money(payment.amount)} a {person} por {data.method}"
                 + (f", ref. {payment.reference}" if payment.reference else "") + f" (planilla #{entry.payroll_period_id})")
    return {"status": "success", "message": f"Pago de {person} registrado"}

@router.post("/confirm")
def confirm_payroll(
    period_id: int = Body(..., embed=True),
    db: Session = Depends(deps.get_db),
    user: User = Depends(deps.get_current_user)
):
    if user.role != ADMIN:
        raise HTTPException(status_code=403, detail="Not authorized")
        
    period = db.query(PayrollPeriod).get(period_id)
    if not period:
        raise HTTPException(status_code=404, detail="Period not found")
        
    period.status = "final"
    db.commit()

    log_activity(db, user, "Aprobar Planilla", "PAYROLL", period.id, f"Planilla #{period.id} aprobada")
    
    return {"status": "success", "message": "Planilla aprobada"}

@router.delete("/{period_id}")
def delete_payroll(
    period_id: int,
    confirm: Optional[str] = None,
    db: Session = Depends(deps.get_db),
    user: User = Depends(deps.get_current_user)
):
    if user.role != ADMIN:
        raise HTTPException(status_code=403, detail="Not authorized")
        
    period = db.query(PayrollPeriod).get(period_id)
    if not period:
        raise HTTPException(status_code=404, detail="Payroll period not found")
    if period.status == "final":
        # A final payroll may be regenerated only while nobody has been paid for it.
        from app.db.models.payment import PayrollPayment
        paid = db.query(PayrollPayment).filter(PayrollPayment.payroll_period_id == period.id).count()
        if paid:
            raise HTTPException(status_code=400, detail=(
                f"Esta planilla final ya tiene {paid} pago(s) registrados y no se puede eliminar."))
        if (confirm or "").strip().upper() != "ELIMINAR":
            raise HTTPException(status_code=400, detail="Para eliminar una planilla final, escribí ELIMINAR.")

    db.delete(period)
    db.commit()

    log_activity(db, user, "Eliminar Planilla", "PAYROLL", period_id, f"Periodo ID: {period_id} eliminado")
    
    return {"status": "success", "message": "Planilla eliminada"}

@router.get("/supervisor/projects")
def get_supervisor_projects(
    db: Session = Depends(deps.get_db),
    user: User = Depends(deps.get_current_user)
):
    if user.role not in [ADMIN, SUPERVISOR]:
        raise HTTPException(status_code=403, detail="Not authorized")
        
    projects = []
    if user.role == SUPERVISOR:
        # Return assigned projects
        # Assuming user.projects is a relationship if setup, OR we need to fetch from Project model
        # The User model has 'projects' relation via project_users table
        projects = user.projects
    else:
        # Admin sees all active projects
        projects = db.query(Project).filter(Project.is_active == True).all()
        
    data = [{"id": p.id, "name": p.name} for p in projects]
    return JSONResponse(data)

@router.get("/schedules")
def get_schedules_for_approval(
    date: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    project_id: Optional[int] = None,
    db: Session = Depends(deps.get_db),
    user: User = Depends(deps.get_current_user)
):
    if user.role not in [ADMIN, SUPERVISOR]:
         raise HTTPException(status_code=403, detail="Not authorized")
    
    query = db.query(ProjectSchedule)

    # Date Logic: Support single date (legacy) or range
    if start_date and end_date:
        s_date = datetime.strptime(start_date, "%Y-%m-%d").date()
        e_date = datetime.strptime(end_date, "%Y-%m-%d").date()
        query = query.filter(ProjectSchedule.date >= s_date, ProjectSchedule.date <= e_date)
    elif date:
        date_val = datetime.strptime(date, "%Y-%m-%d").date()
        query = query.filter(ProjectSchedule.date == date_val)
    else:
        # Default to today if nothing provided? Or return empty?
        # Let's default to today for safety if nothing is provided
        today = datetime.now().date()
        query = query.filter(ProjectSchedule.date == today)

    if project_id:
        query = query.filter(ProjectSchedule.project_id == project_id)
    
    # Supervisors see only their projects check
    if user.role == SUPERVISOR:
        supervisor_project_ids = [p.id for p in user.projects]
        if project_id and project_id not in supervisor_project_ids:
             raise HTTPException(status_code=403, detail="Project not assigned to supervisor")
             
        if not project_id:
             query = query.filter(ProjectSchedule.project_id.in_(supervisor_project_ids))

        # Prevent seeing own records (Self-approval not allowed)
        # These must be approved by Admin
        query = query.filter(ProjectSchedule.user_id != user.id)
        
    # Order by date desc, then worker
    query = query.order_by(ProjectSchedule.date.desc(), ProjectSchedule.user_id)

    schedules = query.all()
    
    data = []
    for s in schedules:
        data.append({
            "id": s.id,
            "project_name": s.project.name if s.project else "Unknown",
            "worker_name": s.user.full_name or s.user.username if s.user else "Unknown",
            "date": s.date.isoformat(),
            "hours_worked": s.hours_worked,
            "overtime_hours": s.overtime_hours,
            "is_confirmed": s.is_confirmed
        })
        
    return JSONResponse(data)

# -----------------------------------------------------------------------------
# 1. HOURS CONFIRMATION (Supervisor / Admin)
# -----------------------------------------------------------------------------

@router.post("/hours/confirm")
def confirm_hours(
    schedule_id: int = Body(..., embed=True),
    hours: float = Body(..., embed=True),
    overtime: float = Body(0.0, embed=True),
    db: Session = Depends(deps.get_db),
    user: User = Depends(deps.get_current_user)
):
    if user.role not in [ADMIN, SUPERVISOR]:
        raise HTTPException(status_code=403, detail="Not authorized")

    schedule = db.query(ProjectSchedule).filter(ProjectSchedule.id == schedule_id).first()
    if not schedule:
        raise HTTPException(status_code=404, detail="Schedule not found")

    set_confirmed_hours(schedule, hours, overtime)
    db.commit()

    log_activity(db, user, "Aprobar Horas", "SCHEDULE", schedule.id, f"Horas: {hours}, Extra: {overtime} para Proyecto: {schedule.project.name if schedule.project else 'Unknown'}")

    return {"status": "success", "message": "Horas confirmadas"}

class ScheduleUpdateItem(pydantic.BaseModel):
    id: int
    hours: float
    overtime: float = 0.0

@router.post("/hours/confirm-batch-update")
def confirm_hours_batch_update(
    updates: List[ScheduleUpdateItem] = Body(...),
    db: Session = Depends(deps.get_db),
    user: User = Depends(deps.get_current_user)
):
    if user.role not in [ADMIN, SUPERVISOR]:
        raise HTTPException(status_code=403, detail="Not authorized")

    count = 0
    for item in updates:
        schedule = db.query(ProjectSchedule).filter(ProjectSchedule.id == item.id).first()
        if schedule:
            if user.role == SUPERVISOR:
                 if schedule.project not in user.projects:
                     continue 
            
            set_confirmed_hours(schedule, item.hours, item.overtime)
            count += 1
            
    db.commit()
    
    log_activity(db, user, "Aprobar Lote", "SCHEDULE", 0, f"Se confirmaron {count} registros")

    return {"status": "success", "message": f"{count} registros confirmados"}

@router.post("/hours/confirm-batch")
def confirm_hours_batch(
    schedule_ids: List[int] = Body(...),
    db: Session = Depends(deps.get_db),
    user: User = Depends(deps.get_current_user)
):
    if user.role not in [ADMIN, SUPERVISOR]:
        raise HTTPException(status_code=403, detail="Not authorized")

    db.query(ProjectSchedule).filter(ProjectSchedule.id.in_(schedule_ids)).update(
        {"is_confirmed": True}, synchronize_session=False
    )
    db.commit()
    return {"status": "success", "message": "Lote confirmado"}

# -----------------------------------------------------------------------------
# 2. PAYROLL GENERATION (Admin)
# -----------------------------------------------------------------------------

# Admin only, checked before the body so other roles get 403 even with an empty request.
@router.post("/generate", dependencies=[Depends(deps.require_roles(ADMIN))])
def generate_payroll(
    start_date: str = Body(...),
    end_date: str = Body(...),
    db: Session = Depends(deps.get_db),
    user: User = Depends(deps.get_current_user)
):
    if user.role != ADMIN:
        raise HTTPException(status_code=403, detail="Not authorized")

    s_date = datetime.strptime(start_date, "%Y-%m-%d").date()
    e_date = datetime.strptime(end_date, "%Y-%m-%d").date()
    if e_date < s_date:
        raise HTTPException(status_code=400, detail="La fecha final es anterior a la inicial")
    # The same hours must never be paid twice: no two payrolls may share a day.
    overlap = db.query(PayrollPeriod).filter(PayrollPeriod.start_date <= e_date,
                                             PayrollPeriod.end_date >= s_date).order_by(PayrollPeriod.id).first()
    if overlap:
        raise HTTPException(status_code=400, detail=(
            f"Ya existe la planilla #{overlap.id} ({overlap.start_date:%d/%m/%Y} – {overlap.end_date:%d/%m/%Y}) "
            "con fechas de este periodo. Elimínela primero o elija otras fechas."))

    # Create Draft Period
    period = PayrollPeriod(
        start_date=s_date,
        end_date=e_date,
        status="draft"
    )
    db.add(period)
    db.flush()

    # Confirmed calendar days, by person.
    schedules = db.query(ProjectSchedule).filter(
        ProjectSchedule.date >= s_date,
        ProjectSchedule.date <= e_date,
        ProjectSchedule.is_confirmed == True
    ).all()
    worked = {}
    for s in schedules:
        data = worked.setdefault(s.user_id, {"hours": 0.0, "overtime": 0.0, "days": set(), "details": []})
        data["hours"] += s.hours_worked or 0.0
        data["overtime"] += s.overtime_hours or 0.0
        if s.hours_worked:
            data["days"].add(s.date)
        data["details"].append({
            "date": s.date.isoformat(),
            "hours": s.hours_worked,
            "overtime": s.overtime_hours,
            "project": s.project.name if s.project else "Unknown",
            "attendance": s.attendance,
        })

    # Monthly people are paid even with no calendar: asesores (ventas) and anyone set to "mensual".
    monthly = db.query(User).filter(User.pay_type == "mensual", User.monthly_salary > 0,
                                    User.role.in_(PAYROLL_PEOPLE)).all()
    people = {p.id: p for p in monthly if deps.can_log_in(p) and not (p.start_date and p.start_date > e_date)}
    # Fixed viáticos are paid each quincena, with or without salary in it.
    for p in db.query(User).filter(User.viatico_quincenal > 0, User.role.in_(PAYROLL_PEOPLE)):
        if deps.can_log_in(p):
            people.setdefault(p.id, p)
    # Adjustments left for the next payroll come in now (pending: no line applies them yet).
    pending = pending_adjustments(db).all()
    for adjustment in pending:
        if adjustment.user:
            people.setdefault(adjustment.user_id, adjustment.user)
    for uid in worked:
        if uid not in people:
            worker = db.get(User, uid)
            if worker:
                people[uid] = worker

    for uid, worker in people.items():
        data = worked.get(uid, {"hours": 0.0, "overtime": 0.0, "days": set(), "details": []})
        pay_type = worker.pay_type or "hora"
        rate = overtime_rate(worker)
        days = len(data["days"])
        if pay_type == "mensual":
            regular_pay = monthly_share(worker.monthly_salary or 0.0, s_date, e_date, worker.start_date)
        elif pay_type == "dia":
            regular_pay = days * (worker.daily_rate or 0.0)
        else:
            rate = worker.hourly_rate or 0.0
            regular_pay = data["hours"] * rate
        overtime_pay = data["overtime"] * rate * 1.5

        # Round Gross to hundreds
        base = round((regular_pay + overtime_pay) / 100) * 100

        entry = PayrollEntry(
            payroll_period_id=period.id,
            user_id=uid,
            total_hours=data["hours"],
            overtime_hours=data["overtime"],
            base_salary=base,
            gross_salary=base,
            apply_deductions=worker.apply_deductions,
            # The overtime base, so the detail can split regular and overtime pay.
            hourly_rate=rate,
            pay_type=pay_type,
            days_worked=days,
            details=data["details"] # JSON
        )
        if worker.viatico_quincenal:
            entry.lines.append(PayrollLine(kind="viatico", description="Viáticos de la quincena",
                                           amount=worker.viatico_quincenal, created_by_id=user.id))
        for adjustment in (a for a in pending if a.user_id == uid):
            source = f" (planilla #{adjustment.source_period_id})" if adjustment.source_period_id else ""
            entry.lines.append(PayrollLine(kind=adjustment.kind, description=adjustment.description + source,
                                           amount=adjustment.amount, adjustment_id=adjustment.id,
                                           created_by_id=user.id))
        recompute(entry)
        # An adjustment that would leave nothing (or less) to pay waits for a later payroll.
        for line in [l for l in entry.lines if l.adjustment_id is not None]:
            if entry.net_salary >= 0:
                break
            if line.amount < 0 or LINE_KINDS[line.kind][1] == "resta":
                entry.lines.remove(line)
                recompute(entry)
        if not (entry.lines or base or data["hours"] or data["overtime"] or uid in worked):
            continue
        db.add(entry)

    db.commit()

    log_activity(db, user, "Generar Planilla", "PAYROLL", period.id, f"Periodo: {start_date} - {end_date}")
    
    return {"status": "success", "message": "Planilla generada (Borrador)", "period_id": period.id}

@router.patch("/entry/{entry_id}")
def update_payroll_entry_deductions(
    entry_id: int,
    apply_deductions: bool = Body(..., embed=True),
    db: Session = Depends(deps.get_db),
    user: User = Depends(deps.get_current_user)
):
    if user.role != ADMIN:
        raise HTTPException(status_code=403, detail="Not authorized")

    entry = db.query(PayrollEntry).get(entry_id)
    if not entry:
        raise HTTPException(status_code=404, detail="Entry not found")
    if entry.period and entry.period.status == "final":
        raise HTTPException(status_code=400, detail="La planilla ya está aprobada: no se puede cambiar")

    log_activity(db, user, "Actualizar Deducciones", "PAYROLL_ENTRY", entry_id, f"Planilla cambio deducciones a: {apply_deductions}")

    entry.apply_deductions = apply_deductions
    recompute(entry)

    db.commit()
    
    return {
        "status": "success", 
        "message": "Actualizado", 
        "net_salary": entry.net_salary,
        "social_charges": entry.social_charges
    }


# -----------------------------------------------------------------------------
# 3. LINES AND ADJUSTMENTS (Admin)
# -----------------------------------------------------------------------------

class LineIn(pydantic.BaseModel):
    kind: str
    description: str = ""
    amount: float


def clean_line(data: LineIn) -> tuple:
    """(kind, description, amount) or an HTTP 400 with the reason."""
    problem = valid_line(data.kind, data.amount)
    if problem:
        raise HTTPException(status_code=400, detail=problem)
    description = (data.description or "").strip()[:200] or LINE_KINDS[data.kind][0]
    return data.kind, description, round(data.amount, 2)


def money(amount: float) -> str:
    return f"{'-' if amount < 0 else ''}₡{abs(amount):,.2f}"


@router.post("/entry/{entry_id}/lines", dependencies=[Depends(deps.require_roles(ADMIN))])
def add_line(entry_id: int, data: LineIn, db: Session = Depends(deps.get_db),
             user: User = Depends(deps.get_current_user)):
    """A bono, deducción, viáticos… on a draft payroll; the person's totals are recalculated."""
    entry = db.get(PayrollEntry, entry_id)
    if not entry:
        raise HTTPException(status_code=404, detail="Entry not found")
    if entry.period.status != "draft":
        raise HTTPException(status_code=400, detail=(
            "La planilla ya está aprobada: no se cambia. Dejá un ajuste para la próxima planilla."))
    kind, description, amount = clean_line(data)
    line = PayrollLine(kind=kind, description=description, amount=amount, created_by_id=user.id)
    entry.lines.append(line)
    recompute(entry)
    if entry.net_salary < 0:
        would_be = entry.net_salary
        db.rollback()
        raise HTTPException(status_code=400, detail=(
            f"El neto quedaría en negativo ({money(would_be)}). Revisá el monto, o dejalo como ajuste para una "
            "planilla con más salario."))
    db.commit()
    log_activity(db, user, "Agregar Línea Planilla", "PAYROLL_ENTRY", entry.id,
                 f"{LINE_KINDS[kind][0]} {money(amount)} a {entry.user.full_name or entry.user.username} "
                 f"en la planilla #{entry.payroll_period_id}: {description}")
    return {"status": "success", "message": "Línea agregada", "net_salary": entry.net_salary}


@router.post("/line/{line_id}/delete", dependencies=[Depends(deps.require_roles(ADMIN))])
def delete_line(line_id: int, db: Session = Depends(deps.get_db), user: User = Depends(deps.get_current_user)):
    line = db.get(PayrollLine, line_id)
    if not line:
        raise HTTPException(status_code=404, detail="Line not found")
    entry = line.entry
    if entry.period.status != "draft":
        raise HTTPException(status_code=400, detail="La planilla ya está aprobada: no se cambia.")
    back = line.adjustment_id is not None
    detail = (f"{LINE_KINDS.get(line.kind, (line.kind,))[0]} {money(line.amount)} de "
              f"{entry.user.full_name or entry.user.username} en la planilla #{entry.payroll_period_id}")
    entry.lines.remove(line)
    recompute(entry)
    db.commit()
    log_activity(db, user, "Quitar Línea Planilla", "PAYROLL_ENTRY", entry.id, detail)
    # A line that came from an adjustment frees it: it waits for the next payroll again.
    message = "Línea quitada" + (": el ajuste vuelve a quedar pendiente para la próxima planilla" if back else "")
    return {"status": "success", "message": message}


class AdjustmentIn(LineIn):
    user_id: int
    source_period_id: Optional[int] = None


@router.post("/adjustments", dependencies=[Depends(deps.require_roles(ADMIN))])
def add_adjustment(data: AdjustmentIn, db: Session = Depends(deps.get_db),
                   user: User = Depends(deps.get_current_user)):
    """For an approved payroll: the correction is left for the person's next payroll, with a record."""
    person = db.get(User, data.user_id)
    if not person:
        raise HTTPException(status_code=404, detail="Persona no encontrada")
    kind, description, amount = clean_line(data)
    if data.source_period_id and not db.get(PayrollPeriod, data.source_period_id):
        raise HTTPException(status_code=404, detail="Planilla no encontrada")
    adjustment = PayrollAdjustment(user_id=person.id, kind=kind, description=description, amount=amount,
                                   source_period_id=data.source_period_id, created_by_id=user.id)
    db.add(adjustment)
    db.commit()
    log_activity(db, user, "Ajuste Planilla", "PAYROLL_ADJUSTMENT", adjustment.id,
                 f"{LINE_KINDS[kind][0]} {money(amount)} para {person.full_name or person.username} en la próxima "
                 f"planilla" + (f" (corrige la #{data.source_period_id})" if data.source_period_id else "")
                 + f": {description}")
    return {"status": "success", "message": "Ajuste guardado: entra en la próxima planilla que se genere"}


@router.post("/adjustments/{adjustment_id}/delete", dependencies=[Depends(deps.require_roles(ADMIN))])
def delete_adjustment(adjustment_id: int, db: Session = Depends(deps.get_db),
                      user: User = Depends(deps.get_current_user)):
    adjustment = db.get(PayrollAdjustment, adjustment_id)
    if not adjustment:
        raise HTTPException(status_code=404, detail="Ajuste no encontrado")
    if adjustment.lines:
        raise HTTPException(status_code=400, detail=(
            f"Ese ajuste ya está en la planilla #{adjustment.lines[0].entry.payroll_period_id}: quitalo de ahí."))
    if db.query(Commission).filter((Commission.adjustment_id == adjustment.id)
                                   | (Commission.reversal_adjustment_id == adjustment.id)).first():
        raise HTTPException(status_code=400, detail="Es una comisión: anulala en Planilla → Comisiones.")
    person = adjustment.user.full_name or adjustment.user.username if adjustment.user else "?"
    detail = f"{LINE_KINDS.get(adjustment.kind, (adjustment.kind,))[0]} {money(adjustment.amount)} para {person}"
    db.delete(adjustment)
    db.commit()
    log_activity(db, user, "Borrar Ajuste Planilla", "PAYROLL_ADJUSTMENT", adjustment_id, detail)
    return {"status": "success", "message": "Ajuste borrado"}


# -----------------------------------------------------------------------------
# 4. COMMISSIONS (Fase 5)
# -----------------------------------------------------------------------------

@router.get("/commissions", response_class=HTMLResponse)
def commissions_view(request: Request, persona: Optional[int] = None, estado: Optional[str] = None,
                     db: Session = Depends(deps.get_db), user: User = Depends(deps.get_current_user)):
    """Admin: every commission, the general rules and Anular. A seller: their own ("Mis comisiones")."""
    if user.role != ADMIN and not user.sells:
        raise HTTPException(status_code=403, detail="Not authorized")
    query = db.query(Commission).order_by(Commission.payment_date.desc().nullslast(), Commission.id.desc())
    if user.role != ADMIN:
        query = query.filter(Commission.user_id == user.id)
    elif persona:
        query = query.filter(Commission.user_id == persona)
    rows = [{"c": c, "status": status_of(c)} for c in query.all()]
    if estado in STATUS_LABELS:
        rows = [r for r in rows if r["status"]["code"] == estado]
    total = sum(r["c"].amount for r in rows if r["status"]["code"] not in ("anulada", "revertida"))
    sellers = []
    if user.role == ADMIN:
        sellers = [{"user": p, "rules": rules_for(db, p)} for p in db.query(User).order_by(User.full_name)
                   if ((p.sells and p.role != ADMIN) or p.commission_percent is not None
                       or p.commission_new_client is not None) and deps.can_log_in(p)]
    # Supervisors who could sell but aren't marked "También vende" (they earn nothing until they are).
    not_selling = [p for p in db.query(User).filter(User.role == SUPERVISOR, User.also_sells == False)  # noqa: E712
                   .order_by(User.full_name) if deps.can_log_in(p)] if user.role == ADMIN else []
    return templates.TemplateResponse("payroll/commissions.html", {
        "not_selling": not_selling,
        "request": request, "user": user, "rows": rows, "total": total, "kinds": COMMISSION_KINDS,
        "status_labels": STATUS_LABELS, "general": general_rules(db), "sellers": sellers,
        "filters": {"persona": persona, "estado": estado},
    })


@router.post("/commissions/settings", dependencies=[Depends(deps.require_roles(ADMIN))])
def commissions_settings(percent: float = Form(0.0), new_client: float = Form(0.0), db: Session = Depends(deps.get_db),
                         user: User = Depends(deps.get_current_user)):
    if percent < 0 or percent > 100 or new_client < 0:
        return RedirectResponse(url="/payroll/commissions?error=valores", status_code=303)
    set_general_rules(db, percent, new_client)
    db.commit()
    log_activity(db, user, "Reglas Comisiones", "COMMISSION", None,
                 f"Generales: {percent:g}% por factura cobrada (sin IVA) y {money(new_client)} por cliente nuevo")
    response = RedirectResponse(url="/payroll/commissions", status_code=303)
    response.set_cookie(key="toast_message", value="Reglas de comisión guardadas")
    return response


class CancelIn(pydantic.BaseModel):
    reason: str = ""


@router.post("/commissions/{commission_id}/cancel", dependencies=[Depends(deps.require_roles(ADMIN))])
def cancel_commission(commission_id: int, data: CancelIn, db: Session = Depends(deps.get_db),
                      user: User = Depends(deps.get_current_user)):
    commission = db.get(Commission, commission_id)
    if not commission:
        raise HTTPException(status_code=404, detail="Comisión no encontrada")
    if not data.reason.strip():
        raise HTTPException(status_code=400, detail="Escribí el motivo")
    try:
        message = cancel(db, commission, data.reason, user)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    db.commit()
    log_activity(db, user, "Anular Comisión", "COMMISSION", commission.id,
                 f"{COMMISSION_KINDS[commission.kind]} {money(commission.amount)} de "
                 f"{commission.user.full_name or commission.user.username} (factura #{commission.invoice_number}): "
                 f"{message}. Motivo: {commission.cancel_reason}")
    return {"status": "success", "message": message}



# -----------------------------------------------------------------------------
# 5. PAID OUTSIDE THE SYSTEM
# -----------------------------------------------------------------------------

@router.post("/{period_id}/paid-outside", dependencies=[Depends(deps.require_roles(ADMIN))])
def mark_paid_outside(period_id: int, db: Session = Depends(deps.get_db), user: User = Depends(deps.get_current_user)):
    """An approved quincena that was paid without recording the payments here (e.g. before the
    system had them): it counts as Pagada, with who said so and when."""
    from datetime import timezone
    period = db.get(PayrollPeriod, period_id)
    if not period:
        raise HTTPException(status_code=404, detail="Payroll period not found")
    if period.status != "final":
        raise HTTPException(status_code=400, detail="Primero aprobá la quincena.")
    status = payment_status(db, period)
    if status["complete"]:
        raise HTTPException(status_code=400, detail="Esa quincena ya está pagada.")
    period.paid_outside_at = datetime.now(timezone.utc)
    period.paid_outside_by_id = user.id
    db.commit()
    log_activity(db, user, "Pagada fuera del sistema", "PAYROLL", period.id,
                 f"Planilla #{period.id} ({period_label(period)}) marcada como pagada fuera del sistema; "
                 f"tenía {status['paid']} de {status['owed']} pagos registrados")
    return {"status": "success", "message": "Quincena marcada como pagada"}


@router.post("/{period_id}/paid-outside/undo", dependencies=[Depends(deps.require_roles(ADMIN))])
def undo_paid_outside(period_id: int, db: Session = Depends(deps.get_db), user: User = Depends(deps.get_current_user)):
    period = db.get(PayrollPeriod, period_id)
    if not period:
        raise HTTPException(status_code=404, detail="Payroll period not found")
    if period.paid_outside_at is None:
        raise HTTPException(status_code=400, detail="Esa quincena no estaba marcada.")
    period.paid_outside_at = None
    period.paid_outside_by_id = None
    db.commit()
    log_activity(db, user, "Deshacer pagada fuera del sistema", "PAYROLL", period.id,
                 f"Planilla #{period.id} ({period_label(period)}) vuelve a esperar sus pagos")
    return {"status": "success", "message": "Listo: la quincena vuelve a esperar sus pagos"}
