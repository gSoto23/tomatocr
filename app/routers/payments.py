
from typing import Optional
from datetime import date
from fastapi import APIRouter, Depends, HTTPException, status, Form, Request
from fastapi.responses import JSONResponse, RedirectResponse
from sqlalchemy.orm import Session
from sqlalchemy import desc

from app.routers import deps
from app.core.roles import ADMIN, OPERATIONS_ROLES, SUPERVISOR, WORKER
from app.db.models.user import User
from app.db.models.payment import PayrollPayment
from app.db.models.payroll import PayrollEntry, PayrollPeriod

PAYMENT_METHODS = ("Sinpe", "Transferencia", "Efectivo")
from app.utils.activity import log_activity

router = APIRouter(
    prefix="/payments",
    tags=["payments"],
    dependencies=[Depends(deps.require_roles(*OPERATIONS_ROLES))]
)

from app.core.templates import templates

@router.get("/", response_class=JSONResponse)
def list_payments_view(
    request: Request,
    db: Session = Depends(deps.get_db), 
    user: User = Depends(deps.get_current_user)
):
    if user.role != ADMIN:
        # Workers and supervisors see their own payments ("Mis pagos")
        if user.role in (WORKER, SUPERVISOR):
            return RedirectResponse(url=f"/payments/history/{user.id}", status_code=303)
        return RedirectResponse(url="/", status_code=303)

    # Admin: List all workers to manage payments
    workers = db.query(User).filter(User.role.in_([WORKER, SUPERVISOR])).all()
    
    return templates.TemplateResponse("payments/index.html", {
        "request": request,
        "user": user,
        "workers": workers
    })

@router.get("/history/{user_id}")
def payment_history(
    user_id: int,
    request: Request,
    db: Session = Depends(deps.get_db),
    user: User = Depends(deps.get_current_user)
):
    # Auth check
    if user.role != ADMIN and user.id != user_id:
        raise HTTPException(status_code=403, detail="Not authorized")
        
    target_user = db.query(User).get(user_id)
    if not target_user:
        raise HTTPException(status_code=404, detail="User not found")
        
    payments = db.query(PayrollPayment)\
        .filter(PayrollPayment.user_id == user_id)\
        .order_by(desc(PayrollPayment.date))\
        .all()
        
    # Final payrolls this person is in, to link a payment to the payroll it settles.
    periods = db.query(PayrollPeriod).join(PayrollEntry).filter(
        PayrollEntry.user_id == user_id, PayrollPeriod.status == "final").order_by(desc(PayrollPeriod.start_date)).all()
    net_by_period = {e.payroll_period_id: e.net_salary for e in
                     db.query(PayrollEntry).filter(PayrollEntry.user_id == user_id)}

    return templates.TemplateResponse("payments/history.html", {
        "request": request,
        "user": user,
        "target_user": target_user,
        "payments": payments,
        "periods": periods,
        "net_by_period": net_by_period,
        "methods": PAYMENT_METHODS,
    })

@router.post("/create")
def create_payment(
    user_id: int = Form(...),
    amount: float = Form(...),
    hours_paid: float = Form(...),
    overtime_hours: float = Form(0.0),
    date_val: str = Form(..., alias="date"),
    notes: Optional[str] = Form(None),
    method: Optional[str] = Form(None),
    reference: Optional[str] = Form(None),
    payroll_period_id: Optional[int] = Form(None),
    db: Session = Depends(deps.get_db),
    user: User = Depends(deps.get_current_user)
):
    if user.role != ADMIN:
        raise HTTPException(status_code=403, detail="Not authorized")

    payment_date = date.fromisoformat(date_val)
    if method not in PAYMENT_METHODS:
        method = None
    if payroll_period_id and not db.query(PayrollEntry).filter(
            PayrollEntry.payroll_period_id == payroll_period_id, PayrollEntry.user_id == user_id).first():
        payroll_period_id = None  # only a payroll this person is in
    
    new_payment = PayrollPayment(
        user_id=user_id,
        amount=amount,
        hours_paid=hours_paid,
        overtime_hours=overtime_hours,
        date=payment_date,
        notes=notes,
        method=method,
        reference=(reference or "").strip()[:100] or None,
        payroll_period_id=payroll_period_id or None,
        created_by_id=user.id
    )
    db.add(new_payment)
    db.commit()
    
    # Log Activity
    target = db.get(User, user_id)
    log_activity(db, user, "CREATE", "PAYMENT", new_payment.id,
                 f"Pago de ₡{amount:,.2f} a {(target.full_name or target.username) if target else user_id}"
                 + (f" por {method}" if method else "") + (f", ref. {new_payment.reference}" if new_payment.reference else ""))
    
    # Redirect back to history
    response = RedirectResponse(url=f"/payments/history/{user_id}", status_code=status.HTTP_303_SEE_OTHER)
    response.set_cookie(key="toast_message", value="Pago registrado correctamente")
    return response
