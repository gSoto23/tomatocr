
from datetime import date
from fastapi import APIRouter, Depends, HTTPException, status, Form, Body, Request
from fastapi.responses import JSONResponse, RedirectResponse, HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from sqlalchemy import desc

from app.db.session import SessionLocal
from app.routers import deps
from app.db.models.user import User
from app.db.models.liquidation import Liquidation
from app.db.models.payment import PayrollPayment
from app.utils.activity import log_activity
from app.core.templates import templates

router = APIRouter(
    prefix="/liquidation",
    tags=["liquidation"],
    dependencies=[Depends(deps.get_current_user)]
)

@router.get("/", response_class=JSONResponse)
async def list_liquidations(
    request: Request,
    db: Session = Depends(deps.get_db), 
    user: User = Depends(deps.get_current_user)
):
    if user.role != "admin":
        # Workers redirect to their own view
        if user.role == "worker":
            return RedirectResponse(url=f"/liquidation/history/{user.id}", status_code=303)
        return RedirectResponse(url="/", status_code=303)

    # Admin: List all workers
    workers = db.query(User).filter(User.role.in_(["worker", "supervisor"])).all()
    
    return templates.TemplateResponse("liquidation/index.html", {
        "request": request,
        "user": user,
        "workers": workers
    })

@router.get("/history/{user_id}")
async def liquidation_history(
    user_id: int,
    request: Request,
    db: Session = Depends(deps.get_db), 
    user: User = Depends(deps.get_current_user)
):
    if user.role != "admin" and user.id != user_id:
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
        "liquidations": liquidations
    })



def calculate_liquidation_data(target_user: User, ref_date: date, db: Session, custom_start_date: date = None):
    # Determines start of unpaid period
    # Use custom_start_date if provided, else user's start_date
    effective_start_date = custom_start_date if custom_start_date else target_user.start_date

    # 1. Vacations
    # Rule: 1 day per month worked.
    vacation_days = 0
    months_worked = 0
    if effective_start_date:
        # Calculate full months
        delta = ref_date - effective_start_date
        if delta.days > 0:
            months_worked = delta.days / 30.44 # Approx
            vacation_days = months_worked # 1 day per month
    
    # Calculate vacation amount
    # (Monthly Salary / 30) * Vacation Days
    vacation_amount = 0.0
    if target_user.monthly_salary:
        daily_salary = target_user.monthly_salary / 30
        vacation_amount = daily_salary * vacation_days

    # 2. Aguinaldo
    # Rule: (Monthly Salary / 12) * Months Worked (Approx simplified)
    # Ideally should sum actual gross salaries since Dec 1st.
    # For now, keeping the estimation as per current logic.
    aguinaldo_amount = (target_user.monthly_salary / 12) * months_worked if months_worked > 0 else 0.0
    
    # 3. Salary Due
    # Unpaid hours since last payment or start date
    # Defaults: 8 hours per day
    salary_due = 0.0
    
    # Determines start of unpaid period
    start_unpaid = effective_start_date
    last_payment = db.query(PayrollPayment).filter(PayrollPayment.user_id == target_user.id).order_by(desc(PayrollPayment.date)).first()
    days_pending = 0
    
    if last_payment:
        # Assume paid up to and including payment date
        start_unpaid = last_payment.date
        # Count days AFTER last payment
        if ref_date > start_unpaid:
            days_pending = (ref_date - start_unpaid).days
    else:
        # Never paid, count from start date inclusive
        if start_unpaid and ref_date >= start_unpaid:
            days_pending = (ref_date - start_unpaid).days + 1
            
    if days_pending > 0:
        daily_hours = 8
        rate = 0.0
        if target_user.hourly_rate:
            rate = target_user.hourly_rate
        elif target_user.monthly_salary:
            rate = target_user.monthly_salary / 30 / 8
            
        salary_due = days_pending * daily_hours * rate
    
    total = vacation_amount + aguinaldo_amount + salary_due
    
    return {
        "user_id": target_user.id,
        "name": target_user.full_name,
        "identity_card": None, # Field does not exist in User model yet
        "start_date": effective_start_date, # Return the one used
        "monthly_salary": target_user.monthly_salary, # Add this
        "months_worked": round(months_worked, 2),
        "vacation_days": round(vacation_days, 2),
        "vacation_amount": round(vacation_amount, 2),
        "aguinaldo_amount": round(aguinaldo_amount, 2),
        "salary_due": round(salary_due, 2),
        "total": round(total, 2),
        "calculation_date": ref_date
    }

@router.get("/preview/{target_user_id}")
async def preview_liquidation(
    target_user_id: int,
    calculation_date: str = None,
    start_date: str = None, # New param
    db: Session = Depends(deps.get_db), 
    user: User = Depends(deps.get_current_user)
):
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="Not authorized")

    target_user = db.query(User).filter(User.id == target_user_id).first()
    if not target_user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Determine reference date
    ref_date = date.today()
    if calculation_date:
        try:
            ref_date = date.fromisoformat(calculation_date)
        except ValueError:
            pass # Fallback to today

    eff_start_date = None
    if start_date:
        try:
            eff_start_date = date.fromisoformat(start_date)
        except ValueError:
            pass

    data = calculate_liquidation_data(target_user, ref_date, db, custom_start_date=eff_start_date)
    return data

@router.get("/letter/{target_user_id}", response_class=HTMLResponse)
async def liquidation_letter(
    target_user_id: int,
    request: Request,
    calculation_date: str = None,
    start_date: str = None, # New param
    db: Session = Depends(deps.get_db),
    user: User = Depends(deps.get_current_user)
):
    if user.role != "admin":
        # Maybe allow the user themselves to see it? For now admin.
        raise HTTPException(status_code=403, detail="Not authorized")

    target_user = db.query(User).filter(User.id == target_user_id).first()
    if not target_user:
        raise HTTPException(status_code=404, detail="User not found")
        
    # Determine reference date
    ref_date = date.today()
    if calculation_date:
        try:
            ref_date = date.fromisoformat(calculation_date)
        except ValueError:
            pass 
            
    eff_start_date = None
    if start_date:
        try:
            eff_start_date = date.fromisoformat(start_date)
        except ValueError:
            pass

    data = calculate_liquidation_data(target_user, ref_date, db, custom_start_date=eff_start_date)
    
    return templates.TemplateResponse("liquidation/letter.html", {
        "request": request,
        "data": data,
        "today": date.today()
    })

@router.post("/create")
async def create_liquidation(
    user_id: int = Form(...),
    date_val: str = Form(..., alias="date"),
    # Form data comes as individual fields, not a dict unless we parse it manually or use Body for JSON.
    # Changing to Form fields for standard POST submission.
    vacation_days: float = Form(0),
    vacation_amount: float = Form(0),
    aguinaldo_amount: float = Form(0),
    salary_due: float = Form(0),
    total: float = Form(0),
    db: Session = Depends(deps.get_db),
    user: User = Depends(deps.get_current_user)
):
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="Not authorized")

    # Save
    liq = Liquidation(
        user_id=user_id,
        date=date.fromisoformat(date_val),
        total_amount=total,
        vacation_days=vacation_days,
        vacation_amount=vacation_amount,
        aguinaldo_amount=aguinaldo_amount,
        salary_due=salary_due,
        created_by_id=user.id
    )
    db.add(liq)
    
    # Mark user as liquidated?
    target_user = db.query(User).get(user_id)
    if target_user:
        target_user.status = "liquidated"
        target_user.is_active = False
        
    db.commit()
    
    log_activity(db, user, "CREATE", "LIQUIDATION", liq.id, f"Liquidated user {user_id}")

    response = RedirectResponse(url=f"/liquidation/history/{user_id}", status_code=status.HTTP_303_SEE_OTHER)
    response.set_cookie(key="toast_message", value="Liquidación registrada y usuario desactivado.")
    return response

@router.post("/reactivate/{target_user_id}")
async def reactivate_user(
    target_user_id: int,
    db: Session = Depends(deps.get_db),
    user: User = Depends(deps.get_current_user)
):
    if user.role != "admin":
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
