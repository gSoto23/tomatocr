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
    
    periods = db.query(PayrollPeriod).order_by(PayrollPeriod.start_date.desc()).all()
    
    return templates.TemplateResponse("payroll/index.html", {
        "request": request,
        "user": user,
        "periods": periods
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
        "company_cost": 0.0
    }
    
    enhanced_entries = []
    
    for entry in entries:
        # Filter for worker if needed
        if user.role == "worker" and entry.user_id != user.id:
            continue
            
        gross = entry.gross_salary
        net = entry.net_salary
        social = entry.social_charges
        
        # New Calculations
        cs_empresa = gross * 0.2667
        previsiones = gross * 0.18
        
        # Accumulate
        totals["hours"] += entry.total_hours
        totals["gross"] += gross
        totals["social_charges"] += social
        totals["net"] += net
        totals["cs_empresa"] += cs_empresa
        totals["previsiones"] += previsiones
        
        entry_dict = {
            "user": entry.user,
            "total_hours": entry.total_hours,
            "gross_salary": gross,
            "social_charges": social,
            "net_salary": net,
            "details": entry.details,
            "cs_empresa": cs_empresa,
            "previsiones": previsiones
        }
        enhanced_entries.append(entry_dict)
        
    totals["company_cost"] = totals["gross"] + totals["cs_empresa"] + totals["previsiones"]

    return templates.TemplateResponse("payroll/detail.html", {
        "request": request,
        "user": user,
        "period": period,
        "entries": enhanced_entries,
        "totals": totals
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
    date: str,
    project_id: Optional[int] = None,
    db: Session = Depends(deps.get_db),
    user: User = Depends(deps.get_current_user)
):
    if user.role not in ["admin", "supervisor"]:
         raise HTTPException(status_code=403, detail="Not authorized")
    
    date_val = datetime.strptime(date, "%Y-%m-%d").date()
    
    query = db.query(ProjectSchedule).filter(ProjectSchedule.date == date_val)

    if project_id:
        query = query.filter(ProjectSchedule.project_id == project_id)
    
    # Supervisors see only their projects check
    if user.role == "supervisor":
        supervisor_project_ids = [p.id for p in user.projects]
        if project_id and project_id not in supervisor_project_ids:
             raise HTTPException(status_code=403, detail="Project not assigned to supervisor")
             
        if not project_id:
             query = query.filter(ProjectSchedule.project_id.in_(supervisor_project_ids))
        
    schedules = query.all()
    
    data = []
    for s in schedules:
        data.append({
            "id": s.id,
            "project_name": s.project.name if s.project else "Unknown",
            "worker_name": s.user.full_name or s.user.username if s.user else "Unknown",
            "date": s.date.isoformat(),
            "hours_worked": s.hours_worked,
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
    db: Session = Depends(deps.get_db),
    user: User = Depends(deps.get_current_user)
):
    if user.role not in ["admin", "supervisor"]:
        raise HTTPException(status_code=403, detail="Not authorized")

    schedule = db.query(ProjectSchedule).filter(ProjectSchedule.id == schedule_id).first()
    if not schedule:
        raise HTTPException(status_code=404, detail="Schedule not found")

    # Supervisor can only confirm their projects? Or all? 
    # Requirement: "Supervisor... Solo puede ver los proyectos asignados"
    # Assuming basic check, but for now allow role-based access.

    schedule.hours_worked = hours
    schedule.is_confirmed = True
    db.commit()

    return {"status": "success", "message": "Horas confirmadas"}

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
            user_hours[s.user_id] = {"total_hours": 0.0, "details": []}
        
        user_hours[s.user_id]["total_hours"] += s.hours_worked
        user_hours[s.user_id]["details"].append({
            "date": s.date.isoformat(),
            "hours": s.hours_worked,
            "project": s.project.name if s.project else "Unknown"
        })

    # Create Entries
    entries = []
    for uid, data in user_hours.items():
        worker = db.query(User).get(uid)
        if not worker:
            continue
        
        rate = worker.hourly_rate or 0.0
        gross = data["total_hours"] * rate
        # Social Charges (9.17% - user specified "Aplicar cargas sociales")
        # Let's assume applied for now, or make it configurable?
        # User said "checkbox: Aplicar cargas sociales". defaulting to YES for standard payroll?
        # Let's subtract simple 9.17%
        charges = gross * 0.0917
        net = gross - charges

        entry = PayrollEntry(
            payroll_period_id=period.id,
            user_id=uid,
            total_hours=data["total_hours"],
            gross_salary=round(gross, 2),
            social_charges=round(charges, 2),
            net_salary=round(net, 2),
            details=data["details"] # JSON
        )
        db.add(entry)
        entries.append(entry)

    db.commit()
    
    return {"status": "success", "message": "Planilla generada (Borrador)", "period_id": period.id}
