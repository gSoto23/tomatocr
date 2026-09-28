
from datetime import date, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status, Form, Request
from fastapi.responses import JSONResponse, RedirectResponse, HTMLResponse
from sqlalchemy.orm import Session
from sqlalchemy import desc

from app.routers import deps
from app.core.roles import ADMIN, OPERATIONS_ROLES, SUPERVISOR, WORKER
from app.db.models.user import User
from app.db.models.liquidation import Liquidation
from app.db.models.payment import PayrollPayment
from app.db.models.payroll import PayrollEntry, PayrollPeriod
from app.db.models.schedule import ProjectSchedule
from app.utils import liquidacion
from app.utils.company import COMPANY, long_date
from app.utils.activity import log_activity
from app.core.templates import templates

router = APIRouter(
    prefix="/liquidation",
    tags=["liquidation"],
    dependencies=[Depends(deps.require_roles(*OPERATIONS_ROLES))]
)

@router.get("/", response_class=JSONResponse)
def list_liquidations(
    request: Request,
    db: Session = Depends(deps.get_db), 
    user: User = Depends(deps.get_current_user)
):
    if user.role != ADMIN:
        # Workers redirect to their own view
        if user.role == WORKER:
            return RedirectResponse(url=f"/liquidation/history/{user.id}", status_code=303)
        return RedirectResponse(url="/", status_code=303)

    # Admin: List all workers
    workers = db.query(User).filter(User.role.in_([WORKER, SUPERVISOR])).all()
    
    return templates.TemplateResponse("liquidation/index.html", {
        "request": request,
        "user": user,
        "workers": workers
    })

@router.get("/history/{user_id}")
def liquidation_history(
    user_id: int,
    request: Request,
    db: Session = Depends(deps.get_db), 
    user: User = Depends(deps.get_current_user)
):
    if user.role != ADMIN and user.id != user_id:
        raise HTTPException(status_code=403, detail="Not authorized")

    target_user = db.query(User).get(user_id)
    if not target_user:
        raise HTTPException(status_code=404, detail="User not found")
        
    liquidations = db.query(Liquidation)\
        .filter(Liquidation.user_id == user_id)\
        .order_by(desc(Liquidation.date))\
        .all()
        
    # Calculate preview if Admin and no liquidation exists? 
    # Or just always allow "New Liquidation" button which opens modal/form.
    
    return templates.TemplateResponse("liquidation/history.html", {
        "request": request,
        "user": user,
        "target_user": target_user,
        "liquidations": liquidations,
        "reasons": liquidacion.REASONS,
    })



AMOUNT_FIELDS = ("vacation_days", "vacation_amount", "aguinaldo_amount", "preaviso_amount", "cesantia_amount",
                 "salary_due", "ccss_deduction", "total")


def parse_day(value: Optional[str], default: Optional[date]) -> Optional[date]:
    try:
        return date.fromisoformat(value) if value else default
    except ValueError:
        return default


def calculate_liquidation_data(target_user: User, ref_date: date, db: Session, custom_start_date: date = None,
                               reason: str = "renuncia", notice_given: bool = False,
                               vacation_days_taken: float = 0) -> dict:
    """Suggested amounts per the Código de Trabajo (app/utils/liquidacion.py)."""
    start = custom_start_date or target_user.start_date
    if start is None:
        raise HTTPException(status_code=400, detail="La persona no tiene fecha de inicio: agréguela en Empleados")
    payrolls = [(period.start_date, period.end_date, entry.gross_salary or 0.0)
                for entry, period in db.query(PayrollEntry, PayrollPeriod)
                .join(PayrollPeriod, PayrollEntry.payroll_period_id == PayrollPeriod.id)
                .filter(PayrollEntry.user_id == target_user.id, PayrollPeriod.status == "final")]
    last_payment = db.query(PayrollPayment).filter(PayrollPayment.user_id == target_user.id)\
        .order_by(desc(PayrollPayment.date)).first()
    unpaid_from = last_payment.date + timedelta(days=1) if last_payment else start
    schedules = db.query(ProjectSchedule).filter(
        ProjectSchedule.user_id == target_user.id, ProjectSchedule.is_confirmed == True,  # noqa: E712
        ProjectSchedule.date >= unpaid_from, ProjectSchedule.date <= ref_date).all()
    pending = (sum(s.hours_worked or 0 for s in schedules), sum(s.overtime_hours or 0 for s in schedules)) \
        if schedules else None
    try:
        result = liquidacion.calculate(
            start, ref_date, reason, target_user.monthly_salary, target_user.hourly_rate, payrolls, pending,
            unpaid_from, vacation_days_taken=vacation_days_taken, notice_given=notice_given,
            apply_deductions=target_user.apply_deductions is not False)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    data = result.as_dict()
    data.update({"user_id": target_user.id, "name": target_user.full_name or target_user.username,
                 "monthly_salary": target_user.monthly_salary or 0.0, "reason_label": liquidacion.REASONS[reason],
                 "notice_given": notice_given, "calculation_date": ref_date.isoformat()})
    return data


def query_options(reason: Optional[str], notice_given: Optional[str], vacation_days_taken: Optional[str]):
    reason = reason if reason in liquidacion.REASONS else "renuncia"
    try:
        taken = max(0.0, float(vacation_days_taken or 0))
    except ValueError:
        taken = 0.0
    return reason, (notice_given or "").lower() in ("1", "true", "on", "si", "sí"), taken


@router.get("/preview/{target_user_id}")
def preview_liquidation(
    target_user_id: int,
    calculation_date: str = None,
    start_date: str = None,
    reason: str = None,
    notice_given: str = None,
    vacation_days_taken: str = None,
    db: Session = Depends(deps.get_db),
    user: User = Depends(deps.get_current_user)
):
    if user.role != ADMIN:
        raise HTTPException(status_code=403, detail="Not authorized")
    target_user = db.query(User).filter(User.id == target_user_id).first()
    if not target_user:
        raise HTTPException(status_code=404, detail="User not found")
    reason, notice, taken = query_options(reason, notice_given, vacation_days_taken)
    return calculate_liquidation_data(target_user, parse_day(calculation_date, date.today()), db,
                                      custom_start_date=parse_day(start_date, None), reason=reason,
                                      notice_given=notice, vacation_days_taken=taken)


@router.get("/letter/{target_user_id}", response_class=HTMLResponse)
def liquidation_letter(
    target_user_id: int,
    request: Request,
    calculation_date: str = None,
    start_date: str = None,
    reason: str = None,
    notice_given: str = None,
    vacation_days_taken: str = None,
    db: Session = Depends(deps.get_db),
    user: User = Depends(deps.get_current_user)
):
    """The letter shows the amounts on screen (the query string), so a corrected amount
    is the one printed; missing ones are calculated."""
    if user.role != ADMIN:
        raise HTTPException(status_code=403, detail="Not authorized")
    target_user = db.query(User).filter(User.id == target_user_id).first()
    if not target_user:
        raise HTTPException(status_code=404, detail="User not found")
    reason, notice, taken = query_options(reason, notice_given, vacation_days_taken)
    ref_date = parse_day(calculation_date, date.today())
    data = calculate_liquidation_data(target_user, ref_date, db, custom_start_date=parse_day(start_date, None),
                                      reason=reason, notice_given=notice, vacation_days_taken=taken)
    for field in AMOUNT_FIELDS:
        value = request.query_params.get(field)
        if value not in (None, ""):
            try:
                data[field] = float(value)
            except ValueError:
                pass
    data["start"] = date.fromisoformat(data["start_date"])
    data["end"] = ref_date
    return templates.TemplateResponse("liquidation/letter.html", {
        "request": request, "data": data, "company": COMPANY, "long_date": long_date(ref_date),
    })


@router.post("/create")
def create_liquidation(
    user_id: int = Form(...),
    date_val: str = Form(..., alias="date"),
    reason: str = Form("renuncia"),
    notice_given: bool = Form(False),
    vacation_days_taken: float = Form(0),
    vacation_days: float = Form(0),
    vacation_amount: float = Form(0),
    aguinaldo_amount: float = Form(0),
    preaviso_amount: float = Form(0),
    cesantia_amount: float = Form(0),
    salary_due: float = Form(0),
    ccss_deduction: float = Form(0),
    db: Session = Depends(deps.get_db),
    user: User = Depends(deps.get_current_user)
):
    if user.role != ADMIN:
        raise HTTPException(status_code=403, detail="Not authorized")
    if reason not in liquidacion.REASONS:
        raise HTTPException(status_code=400, detail="Motivo de salida no válido")
    # The total is recomputed here from the (possibly corrected) amounts, never trusted from the form.
    total = round(vacation_amount + aguinaldo_amount + preaviso_amount + cesantia_amount + salary_due
                  - ccss_deduction, 2)
    liq = Liquidation(
        user_id=user_id, date=date.fromisoformat(date_val), total_amount=total, vacation_days=vacation_days,
        vacation_amount=vacation_amount, aguinaldo_amount=aguinaldo_amount, salary_due=salary_due, reason=reason,
        notice_given=notice_given, vacation_days_taken=vacation_days_taken, preaviso_amount=preaviso_amount,
        cesantia_amount=cesantia_amount, ccss_deduction=ccss_deduction, created_by_id=user.id,
    )
    db.add(liq)
    target_user = db.query(User).get(user_id)
    if target_user:
        target_user.status = "liquidated"
        target_user.is_active = False
    db.commit()
    log_activity(db, user, "CREATE", "LIQUIDATION", liq.id,
                 f"Liquidación de {target_user.full_name if target_user else user_id}: ₡{total:,.2f} "
                 f"({liquidacion.REASONS[reason]})")
    response = RedirectResponse(url=f"/liquidation/history/{user_id}", status_code=status.HTTP_303_SEE_OTHER)
    response.set_cookie(key="toast_message", value="Liquidación registrada y usuario desactivado.")
    return response

@router.post("/reactivate/{target_user_id}")
def reactivate_user(
    target_user_id: int,
    db: Session = Depends(deps.get_db),
    user: User = Depends(deps.get_current_user)
):
    if user.role != ADMIN:
        raise HTTPException(status_code=403, detail="Not authorized")

    target_user = db.query(User).get(target_user_id)
    if not target_user:
        raise HTTPException(status_code=404, detail="User not found")
        
    if target_user.status != "liquidated":
        raise HTTPException(status_code=400, detail="User is not liquidated")

    # Reactivate
    target_user.status = "active"
    target_user.is_active = True
    target_user.start_date = date.today() # Reset start date to today (Re-hire)
    
    db.commit()
    
    log_activity(db, user, "UPDATE", "USER", target_user.id, f"Reactivated user {target_user.full_name}")
    
    response = RedirectResponse(url=f"/liquidation/history/{target_user_id}", status_code=status.HTTP_303_SEE_OTHER)
    response.set_cookie(key="toast_message", value="Usuario reactivado correctamente.")
    return response
