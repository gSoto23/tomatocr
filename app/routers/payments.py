
from typing import List, Optional
from datetime import date
from fastapi import APIRouter, Depends, HTTPException, status, Form, Body, Request
from fastapi.responses import JSONResponse, RedirectResponse
from sqlalchemy.orm import Session
from sqlalchemy import desc

from app.db.session import SessionLocal
from app.routers import deps
from app.db.models.user import User
from app.db.models.payment import PayrollPayment
from app.utils.activity import log_activity

router = APIRouter(
    prefix="/payments",
    tags=["payments"],
    dependencies=[Depends(deps.get_current_user)]
)

from fastapi.templating import Jinja2Templates
from app.core.templates import templates
from fastapi import Request

@router.get("/", response_class=JSONResponse)
async def list_payments_view(
    request: Request,
    db: Session = Depends(deps.get_db), 
    user: User = Depends(deps.get_current_user)
):
    if user.role != "admin":
        # Workers redirect to their own history
        if user.role == "worker":
            return RedirectResponse(url=f"/payments/history/{user.id}", status_code=303)
        return RedirectResponse(url="/", status_code=303)

    # Admin: List all workers to manage payments
    workers = db.query(User).filter(User.role.in_(["worker", "supervisor"])).all()
    
    return templates.TemplateResponse("payments/index.html", {
        "request": request,
        "user": user,
        "workers": workers
    })

@router.get("/history/{user_id}")
async def payment_history(
    user_id: int,
    request: Request,
    db: Session = Depends(deps.get_db),
    user: User = Depends(deps.get_current_user)
):
    # Auth check
    if user.role != "admin" and user.id != user_id:
        raise HTTPException(status_code=403, detail="Not authorized")
        
    target_user = db.query(User).get(user_id)
    if not target_user:
        raise HTTPException(status_code=404, detail="User not found")
        
    payments = db.query(PayrollPayment)\
        .filter(PayrollPayment.user_id == user_id)\
        .order_by(desc(PayrollPayment.date))\
        .all()
        
    return templates.TemplateResponse("payments/history.html", {
        "request": request,
        "user": user,
        "target_user": target_user,
        "payments": payments
    })

@router.post("/create")
async def create_payment(
    user_id: int = Form(...),
    amount: float = Form(...),
    hours_paid: float = Form(...),
    overtime_hours: float = Form(0.0),
    date_val: str = Form(..., alias="date"),
    notes: Optional[str] = Form(None),
    db: Session = Depends(deps.get_db),
    user: User = Depends(deps.get_current_user)
):
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="Not authorized")

    payment_date = date.fromisoformat(date_val)
    
    new_payment = PayrollPayment(
        user_id=user_id,
        amount=amount,
        hours_paid=hours_paid,
        overtime_hours=overtime_hours,
        date=payment_date,
        notes=notes,
        created_by_id=user.id
    )
    db.add(new_payment)
    db.commit()
    
    # Log Activity
    log_activity(db, user, "CREATE", "PAYMENT", new_payment.id, f"Paid {amount} to user {user_id}")
    
    # Redirect back to history
    response = RedirectResponse(url=f"/payments/history/{user_id}", status_code=status.HTTP_303_SEE_OTHER)
    response.set_cookie(key="toast_message", value="Pago registrado correctamente")
    return response
