from typing import List, Optional
from datetime import date, datetime
from fastapi import APIRouter, Depends, HTTPException, status, Form, Body, Request
from fastapi.responses import JSONResponse, HTMLResponse
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.db.session import SessionLocal
from app.routers import deps
from app.db.models.user import User
from app.db.models.schedule import ProjectSchedule
from app.db.models.payroll import PayrollPeriod, PayrollEntry
import pydantic
from app.db.models.project import Project
from app.utils.activity import log_activity
from app.core.templates import templates

router = APIRouter(
    prefix="/payroll",
    tags=["payroll"],
    dependencies=[Depends(deps.get_current_user)]
)

@router.get("/", response_class=HTMLResponse)
async def payroll_dashboard(
    request: Request,
    db: Session = Depends(deps.get_db),
    user: User = Depends(deps.get_current_user)
):
    if user.role not in ["admin", "supervisor", "worker"]:
         raise HTTPException(status_code=403, detail="Not authorized")
    
    # Admin: Full dashboard
    # Supervisor: Approval view redirect? Or dashboard with limited options?
    # Worker: My payments/payroll?
    
    query = db.query(PayrollPeriod).order_by(PayrollPeriod.start_date.desc())
    
    if user.role in ["worker", "supervisor"]:
        # Only periods where user has an entry, OR allows seeing active/draft if they are scheduled?
        # Usually they only see finalized payrolls or drafts where they are calculated.
        # Filtering by existence of PayrollEntry for this user
        query = query.join(PayrollEntry).filter(PayrollEntry.user_id == user.id)
        
    periods = query.all()

    # Calculate stats for Worker/Supervisor
    worker_stats = {}
    if user.role in ["worker", "supervisor"]:
        vacation_days = 0
        if user.start_date:
            delta = date.today() - user.start_date
            if delta.days > 0:
                months_worked = delta.days / 30.44
                vacation_days = months_worked 
        worker_stats["vacation_days"] = round(vacation_days, 2)
    
    return templates.TemplateResponse("payroll/index.html", {
        "request": request,
        "user": user,
        "periods": periods,
        "worker_stats": worker_stats
    })

@router.get("/approval", response_class=HTMLResponse)
async def approval_view(
    request: Request,
    db: Session = Depends(deps.get_db),
    user: User = Depends(deps.get_current_user)
):
    if user.role not in ["admin", "supervisor"]:
         raise HTTPException(status_code=403, detail="Not authorized")
         
    # Fetch unconfirmed past schedules? Or all for a range?
    # Let's show unconfirmed logic in the template or fetch here.
    # For now, just serve the page.
    return templates.TemplateResponse("payroll/approval.html", {
        "request": request,
        "user": user
    })


@router.get("/detail/{period_id}", response_class=HTMLResponse)
async def payroll_detail(
    period_id: int,
    request: Request,
    db: Session = Depends(deps.get_db),
    user: User = Depends(deps.get_current_user)
):
    if user.role not in ["admin", "supervisor", "worker"]:
         raise HTTPException(status_code=403, detail="Not authorized")

    period = db.query(PayrollPeriod).filter(PayrollPeriod.id == period_id).first()
    if not period:
        raise HTTPException(status_code=404, detail="Payroll period not found")
        
    entries = db.query(PayrollEntry).filter(PayrollEntry.payroll_period_id == period_id).all()
    
    # Calculate extra columns and totals
    totals = {
        "hours": 0.0,
        "gross": 0.0,
        "social_charges": 0.0,
        "net": 0.0,
        "cs_empresa": 0.0,
        "previsiones": 0.0,
        "company_cost": 0.0,
        "regular_amount": 0.0,
        "overtime_amount": 0.0,
        "overtime_hours": 0.0
    }
    
    enhanced_entries = []
    
    for entry in entries:
        # Filter for worker/supervisor (only see own)
        if user.role in ["worker", "supervisor"] and entry.user_id != user.id:
            continue
            
        gross = entry.gross_salary
        net = entry.net_salary
        social = entry.social_charges
        
        # Split Amounts (Recalculate approximate split, ensuring sum matches gross)
        rate = entry.user.hourly_rate or 0.0
        # Round overtime to hundreds to match generation logic
        overtime_amt = 0.0
        if entry.overtime_hours:
            overtime_amt = round((entry.overtime_hours * rate * 1.5) / 100) * 100
        
        regular_amt = gross - overtime_amt
        
        # New Calculations
        cs_empresa = gross * 0.2667
        previsiones = gross * 0.18
        
        # Accumulate
        totals["hours"] += entry.total_hours
        totals["overtime_hours"] += (entry.overtime_hours or 0.0)
        totals["gross"] += gross
        totals["social_charges"] += social
        totals["net"] += net
        totals["cs_empresa"] += cs_empresa
        totals["previsiones"] += previsiones
        totals["regular_amount"] += regular_amt
        totals["overtime_amount"] += overtime_amt
        
        entry_dict = {
            "user": entry.user,
            "total_hours": entry.total_hours,
            "gross_salary": gross,
            "social_charges": social,
            "net_salary": net,
            "details": entry.details,
            "cs_empresa": cs_empresa,
            "previsiones": previsiones,
            "apply_deductions": entry.apply_deductions,
            "regular_amount": regular_amt,
            "overtime_amount": overtime_amt,
            "overtime_hours": entry.overtime_hours or 0.0
        }
        enhanced_entries.append(entry_dict)
        
    totals["company_cost"] = totals["gross"] + totals["cs_empresa"] + totals["previsiones"]

    # For Worker/Supervisor view: Calculate Vacation Days
    worker_stats = {}
    if user.role in ["worker", "supervisor"]:
        # Logic from liquidation: 1 day per month worked
        vacation_days = 0
        if user.start_date:
            delta = date.today() - user.start_date
            if delta.days > 0:
                months_worked = delta.days / 30.44
                vacation_days = months_worked # 1 day per month
        worker_stats["vacation_days"] = round(vacation_days, 2)

    return templates.TemplateResponse("payroll/detail.html", {
        "request": request,
        "user": user,
        "period": period,
        "entries": enhanced_entries,
        "totals": totals,
        "worker_stats": worker_stats
    })

@router.get("/report/{period_id}", response_class=HTMLResponse)
async def payroll_report(
    period_id: int,
    request: Request,
    db: Session = Depends(deps.get_db),
    user: User = Depends(deps.get_current_user)
):
    if user.role not in ["admin", "supervisor", "worker"]:
         raise HTTPException(status_code=403, detail="Not authorized")

    period = db.query(PayrollPeriod).filter(PayrollPeriod.id == period_id).first()
    if not period:
        raise HTTPException(status_code=404, detail="Payroll period not found")
        
    entries = db.query(PayrollEntry).filter(PayrollEntry.payroll_period_id == period_id).all()
    
    report_data = []
    total_net = 0.0

    for entry in entries:
        # Filter logic: Admin sees all. Worker/Supervisor sees only own.
        if user.role in ["worker", "supervisor"] and entry.user_id != user.id:
            continue
        
        # Calculate overtime amount approx (or use what we stored if we stored it? We didn't stored overtime_pay separately)
        # Using current rate might be slightly off if rate changed, but best effort.
        rate = entry.user.hourly_rate or 0.0
        overtime_hours = entry.overtime_hours or 0.0
        overtime_amount = overtime_hours * rate * 1.5
        
        report_data.append({
            "name": entry.user.full_name or entry.user.username,
            "phone": entry.user.phone or "N/A",
            "hours": entry.total_hours,
            "overtime_hours": overtime_hours,
            "overtime_amount": overtime_amount,
            "net_pay": entry.net_salary,
            "payment_method": entry.user.payment_method,
            "account_number": entry.user.account_number
        })
        total_net += entry.net_salary
        
    return templates.TemplateResponse("payroll/report.html", {
        "request": request,
        "period": period,
        "entries": report_data,
        "total_net": total_net,
        "today": date.today()
    })

@router.post("/confirm")
async def confirm_payroll(
    period_id: int = Body(..., embed=True),
    db: Session = Depends(deps.get_db),
    user: User = Depends(deps.get_current_user)
):
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="Not authorized")
        
    period = db.query(PayrollPeriod).get(period_id)
    if not period:
        raise HTTPException(status_code=404, detail="Period not found")
        
    period.status = "final"
    db.commit()

    log_activity(db, user, "Finalizar Planilla", "PAYROLL", period.id, f"Periodo ID: {period.id} finalizado")
    
    return {"status": "success", "message": "Planilla finalizada"}

@router.delete("/{period_id}")
async def delete_payroll(
    period_id: int,
    db: Session = Depends(deps.get_db),
    user: User = Depends(deps.get_current_user)
):
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="Not authorized")
        
    period = db.query(PayrollPeriod).get(period_id)
    if not period:
        raise HTTPException(status_code=404, detail="Payroll period not found")
        
    db.delete(period)
    db.commit()

    log_activity(db, user, "Eliminar Planilla", "PAYROLL", period_id, f"Periodo ID: {period_id} eliminado")
    
    return {"status": "success", "message": "Planilla eliminada"}

@router.get("/supervisor/projects")
async def get_supervisor_projects(
    db: Session = Depends(deps.get_db),
    user: User = Depends(deps.get_current_user)
):
    if user.role not in ["admin", "supervisor"]:
        raise HTTPException(status_code=403, detail="Not authorized")
        
    projects = []
    if user.role == "supervisor":
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
async def get_schedules_for_approval(
    date: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    project_id: Optional[int] = None,
    db: Session = Depends(deps.get_db),
    user: User = Depends(deps.get_current_user)
):
    if user.role not in ["admin", "supervisor"]:
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
    if user.role == "supervisor":
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
async def confirm_hours(
    schedule_id: int = Body(..., embed=True),
    hours: float = Body(..., embed=True),
    overtime: float = Body(0.0, embed=True),
    db: Session = Depends(deps.get_db),
    user: User = Depends(deps.get_current_user)
):
    if user.role not in ["admin", "supervisor"]:
        raise HTTPException(status_code=403, detail="Not authorized")

    schedule = db.query(ProjectSchedule).filter(ProjectSchedule.id == schedule_id).first()
    if not schedule:
        raise HTTPException(status_code=404, detail="Schedule not found")

    schedule.hours_worked = hours
    schedule.overtime_hours = overtime
    schedule.is_confirmed = True
    db.commit()

    log_activity(db, user, "Aprobar Horas", "SCHEDULE", schedule.id, f"Horas: {hours}, Extra: {overtime} para Proyecto: {schedule.project.name if schedule.project else 'Unknown'}")

    return {"status": "success", "message": "Horas confirmadas"}

class ScheduleUpdateItem(pydantic.BaseModel):
    id: int
    hours: float
    overtime: float = 0.0

@router.post("/hours/confirm-batch-update")
async def confirm_hours_batch_update(
    updates: List[ScheduleUpdateItem] = Body(...),
    db: Session = Depends(deps.get_db),
    user: User = Depends(deps.get_current_user)
):
    if user.role not in ["admin", "supervisor"]:
        raise HTTPException(status_code=403, detail="Not authorized")

    count = 0
    for item in updates:
        schedule = db.query(ProjectSchedule).filter(ProjectSchedule.id == item.id).first()
        if schedule:
            if user.role == "supervisor":
                 if schedule.project not in user.projects:
                     continue 
            
            schedule.hours_worked = item.hours
            schedule.overtime_hours = item.overtime
            schedule.is_confirmed = True
            count += 1
            
    db.commit()
    
    log_activity(db, user, "Aprobar Lote", "SCHEDULE", 0, f"Se confirmaron {count} registros")

    return {"status": "success", "message": f"{count} registros confirmados"}

@router.post("/hours/confirm-batch")
async def confirm_hours_batch(
    schedule_ids: List[int] = Body(...),
    db: Session = Depends(deps.get_db),
    user: User = Depends(deps.get_current_user)
):
    if user.role not in ["admin", "supervisor"]:
        raise HTTPException(status_code=403, detail="Not authorized")

    db.query(ProjectSchedule).filter(ProjectSchedule.id.in_(schedule_ids)).update(
        {"is_confirmed": True}, synchronize_session=False
    )
    db.commit()
    return {"status": "success", "message": "Lote confirmado"}

# -----------------------------------------------------------------------------
# 2. PAYROLL GENERATION (Admin)
# -----------------------------------------------------------------------------

@router.post("/generate")
async def generate_payroll(
    start_date: str = Body(...),
    end_date: str = Body(...),
    db: Session = Depends(deps.get_db),
    user: User = Depends(deps.get_current_user)
):
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="Not authorized")

    s_date = datetime.strptime(start_date, "%Y-%m-%d").date()
    e_date = datetime.strptime(end_date, "%Y-%m-%d").date()

    # Create Draft Period
    period = PayrollPeriod(
        start_date=s_date,
        end_date=e_date,
        status="draft"
    )
    db.add(period)
    db.flush()

    # Calculate for each worker
    # Get all confirmed schedules in range
    schedules = db.query(ProjectSchedule).filter(
        ProjectSchedule.date >= s_date,
        ProjectSchedule.date <= e_date,
        ProjectSchedule.is_confirmed == True
    ).all()

    # Group by User
    user_hours = {}
    for s in schedules:
        if s.user_id not in user_hours:
            user_hours[s.user_id] = {"total_hours": 0.0, "overtime_hours": 0.0, "details": []}
        
        user_hours[s.user_id]["total_hours"] += s.hours_worked
        user_hours[s.user_id]["overtime_hours"] += (getattr(s, "overtime_hours", 0.0) or 0.0)
        user_hours[s.user_id]["details"].append({
            "date": s.date.isoformat(),
            "hours": s.hours_worked,
            "overtime": s.overtime_hours,
            "project": s.project.name if s.project else "Unknown"
        })

    # Create Entries
    entries = []
    for uid, data in user_hours.items():
        worker = db.query(User).get(uid)
        if not worker:
            continue
        
        rate = worker.hourly_rate or 0.0
        # Calculate separately
        regular_pay = data["total_hours"] * rate
        overtime_pay = data["overtime_hours"] * rate * 1.5
        
        # Round Gross to hundreds
        gross = round((regular_pay + overtime_pay) / 100) * 100
        
        # Social Charges (9.17% - user specified "Aplicar cargas sociales")
        charges = 0.0
        if worker.apply_deductions:
             charges = round((gross * 0.0917) / 100) * 100
        
        net = gross - charges

        entry = PayrollEntry(
            payroll_period_id=period.id,
            user_id=uid,
            total_hours=data["total_hours"],
            overtime_hours=data["overtime_hours"],
            gross_salary=gross,
            social_charges=charges,
            net_salary=net,
            apply_deductions=worker.apply_deductions,
            details=data["details"] # JSON
        )
        db.add(entry)
        entries.append(entry)

    db.commit()

    log_activity(db, user, "Generar Planilla", "PAYROLL", period.id, f"Periodo: {start_date} - {end_date}")
    
    return {"status": "success", "message": "Planilla generada (Borrador)", "period_id": period.id}

@router.patch("/entry/{entry_id}")
async def update_payroll_entry_deductions(
    entry_id: int,
    apply_deductions: bool = Body(..., embed=True),
    db: Session = Depends(deps.get_db),
    user: User = Depends(deps.get_current_user)
):
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="Not authorized")

    entry = db.query(PayrollEntry).get(entry_id)
    if not entry:
        raise HTTPException(status_code=404, detail="Entry not found")

    log_activity(db, user, "Actualizar Deducciones", "PAYROLL_ENTRY", entry_id, f"Planilla cambio deducciones a: {apply_deductions}")

    entry.apply_deductions = apply_deductions
    
    # Recalculate with rounding
    # Note: gross_salary is already rounded from creation, but if we want to be safe we use it as is.
    gross = entry.gross_salary 
    charges = 0.0
    if apply_deductions:
        charges = round((gross * 0.0917) / 100) * 100
        
    entry.social_charges = charges
    entry.net_salary = gross - charges
    
    db.commit()
    
    return {
        "status": "success", 
        "message": "Actualizado", 
        "net_salary": entry.net_salary,
        "social_charges": entry.social_charges
    }
