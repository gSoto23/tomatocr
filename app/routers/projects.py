
from typing import List, Optional
from fastapi import APIRouter, Depends, Request, status, HTTPException
from fastapi.responses import RedirectResponse, JSONResponse
from sqlalchemy.orm import Session
from pydantic import BaseModel

from app.db.models.project import Project
from app.db.models.project_details import ProjectSupply, ProjectTask, ProjectContact, ProjectLocation
from app.db.models.finance import ProjectBudget, BudgetLine, ProjectCost
from app.db.models.schedule import ProjectSchedule
from app.db.models.user import User
from app.db.models.log import DailyLog
from app.db.models.reforestation import ReforestationProject
from app.db.models.crm import Account, Opportunity
from app.utils.crm import account_payload, project_contact_roles, set_project_contacts, site_contacts, win_opportunity
from app.db.models.associations import project_users
from sqlalchemy import desc, func
from math import ceil
from app.routers import deps
from app.core.roles import ADMIN, CLIENT, OPERATIONS_ROLES, SUPERVISOR, WORKER
from app.utils.activity import log_activity
import logging

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/projects",
    tags=["projects"],
    dependencies=[Depends(deps.require_roles(*OPERATIONS_ROLES))]
)

from app.core.templates import templates

# Pydantic Models for JSON body
class SupplyCreate(BaseModel):
    name: str
    quantity: str

class TaskCreate(BaseModel):
    description: str
    is_required: bool = True

class LocationCreate(BaseModel):
    name: str
    location: Optional[str] = None
    waze_pin: Optional[str] = None

class ContactCreate(BaseModel):
    name: str
    phone: Optional[str] = None
    email: Optional[str] = None
    position: Optional[str] = None

class ContactRoleIn(BaseModel):
    contact_id: int
    is_site: bool = True
    receives_reports: bool = False
    position: Optional[str] = None

class BudgetLineCreate(BaseModel):
    name: str
    subtotal: float
    tax_percentage: float = 13.0

class ProjectCreate(BaseModel):
    name: str
    client_ids: List[int] = []
    worker_ids: List[int] = []
    client_display_name: Optional[str] = None
    province: Optional[str] = None
    address: Optional[str] = None
    waze_link: Optional[str] = None
    description: Optional[str] = None
    # Client account (Clientes) and which of its contacts the project uses.
    account_id: Optional[int] = None
    contact_roles: List[ContactRoleIn] = []
    opportunity_id: Optional[int] = None  # set when the project is created from a won opportunity
    # Lists
    contacts: List[ContactCreate] = []  # old per-project contacts; no longer sent by the form
    supplies: List[SupplyCreate] = []
    tasks: List[TaskCreate] = []
    locations: List[LocationCreate] = []
    is_active: bool = True
    # Budget Information
    licitation_number: Optional[str] = None
    contract_duration: Optional[str] = None
    is_prorrogable: bool = False
    active_prorogue: bool = False
    prorrogable_time: Optional[str] = None
    prorrogable_amount: Optional[float] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    budget_lines: List[BudgetLineCreate] = []

@router.get("/")
def list_projects(
    request: Request, 
    page: int = 1, 
    limit: int = 10,
    db: Session = Depends(deps.get_db), 
    user: User = Depends(deps.get_current_user)
):
    offset = (page - 1) * limit
    
    if user.role == ADMIN:
        count_query = db.query(func.count(Project.id))
        total_records = count_query.scalar()
        
        projects = db.query(Project)\
            .order_by(Project.id.desc())\
            .offset(offset)\
            .limit(limit)\
            .all()
    else:
        # Explicit query
        count_query = db.query(func.count(Project.id))\
            .join(project_users)\
            .filter(project_users.c.user_id == user.id)
        total_records = count_query.scalar()
        
        projects = db.query(Project)\
            .join(project_users)\
            .filter(project_users.c.user_id == user.id)\
            .order_by(Project.id.desc())\
            .offset(offset)\
            .limit(limit)\
            .all()
    
    from math import ceil
    total_pages = ceil(total_records / limit)
    
    return templates.TemplateResponse("projects/list.html", {
        "request": request, 
        "projects": projects, 
        "user": user,
        "page": page,
        "total_pages": total_pages,
        "total_records": total_records
    })

def apply_account(db: Session, project: Project, project_in: "ProjectCreate"):
    """Every project belongs to a client account; its contacts come from that account."""
    account = db.get(Account, project_in.account_id) if project_in.account_id else None
    if account is None or account.merged_into_id:
        raise HTTPException(status_code=400, detail="Elija la cuenta del cliente (o créela) antes de guardar.")
    project.account_id = account.id
    project.client_display_name = account.name  # kept in sync for screens and reports that show it
    set_project_contacts(db, project, account, [r.dict() for r in project_in.contact_roles])
    return account


def account_form_data(db: Session, project: Optional[Project]):
    account = db.get(Account, project.account_id) if project and project.account_id else None
    roles = [{"contact_id": r.contact_id, "is_site": r.is_site, "receives_reports": r.receives_reports,
              "position": r.position or ""} for r in project_contact_roles(db, project.id)] if project else []
    return (account_payload(account) if account else None), roles


@router.get("/new")
def new_project_form(request: Request, opportunity_id: Optional[int] = None, db: Session = Depends(deps.get_db),
                     user: User = Depends(deps.get_current_user)):
    if user.role != ADMIN: 
        return RedirectResponse(url="/projects", status_code=status.HTTP_303_SEE_OTHER)

    clients = db.query(User).filter(User.role == CLIENT).all()
    workers = db.query(User).filter(User.role.in_([WORKER, SUPERVISOR])).all()
    opportunity = db.get(Opportunity, opportunity_id) if opportunity_id else None
    account = db.get(Account, opportunity.account_id) if opportunity else None
    
    return templates.TemplateResponse("projects/form.html", {
        "request": request, 
        "user": user, 
        "project": None, 
        "clients": clients,
        "workers": workers,
        "account": account_payload(account) if account else None,
        "contact_roles": [],
        "opportunity": opportunity,
    })

@router.post("/new")
def create_project(
    project_in: ProjectCreate,
    db: Session = Depends(deps.get_db),
    user: User = Depends(deps.get_current_user)
):
    if user.role != ADMIN:
         raise HTTPException(status_code=403, detail="Not authorized")

    project = Project(
        name=project_in.name,
        client_display_name=project_in.client_display_name,
        province=project_in.province,
        address=project_in.address,
        waze_link=project_in.waze_link,
        description=project_in.description,
        is_active=project_in.is_active
    )
    
    # Assign users
    all_ids = project_in.client_ids + project_in.worker_ids
    if all_ids:
        selected_users = db.query(User).filter(User.id.in_(all_ids)).all()
        project.users = selected_users

    db.add(project)
    db.flush() # get ID
    apply_account(db, project, project_in)
    if project_in.opportunity_id:
        opportunity = db.get(Opportunity, project_in.opportunity_id)
        if opportunity is None:
            raise HTTPException(status_code=400, detail="La oportunidad no existe")
        try:
            win_opportunity(db, opportunity, project, user)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))

    # Add Supplies
    for s in project_in.supplies:
        db.add(ProjectSupply(project_id=project.id, name=s.name, quantity=s.quantity))

    # Add Tasks
    for t in project_in.tasks:
        db.add(ProjectTask(project_id=project.id, description=t.description, is_required=t.is_required))

    # Add Locations
    for loc in project_in.locations:
        db.add(ProjectLocation(project_id=project.id, name=loc.name, location=loc.location, waze_pin=loc.waze_pin))

    # Add Budget Info
    import datetime
    
    start_date_obj = None
    if project_in.start_date:
        start_date_obj = datetime.datetime.strptime(project_in.start_date, "%Y-%m-%d").date()

    end_date_obj = None
    if project_in.end_date:
        end_date_obj = datetime.datetime.strptime(project_in.end_date, "%Y-%m-%d").date()

    budget = ProjectBudget(
        project_id=project.id,
        licitation_number=project_in.licitation_number,
        contract_duration=project_in.contract_duration,
        is_prorrogable=project_in.is_prorrogable,
        active_prorogue=project_in.active_prorogue if project_in.is_prorrogable else False,
        prorrogable_time=project_in.prorrogable_time,
        prorrogable_amount=project_in.prorrogable_amount or 0.0,
        start_date=start_date_obj,
        end_date=end_date_obj
    )
    db.add(budget)
    db.flush()

    for line in project_in.budget_lines:
        db.add(BudgetLine(
            budget_id=budget.id,
            name=line.name,
            subtotal=line.subtotal,
            tax_percentage=line.tax_percentage
        ))

    db.commit()
    
    # Audit Log
    try:
        log_activity(db, user=user, action="CREATE", entity_type="PROJECT", entity_id=project.id, details=f"Creado proyecto {project.name}")
    except Exception as e:
        logger.error(f"Audit Log Error: {e}")
        
    # Return JSON redirect instruction with Toast Cookie
    response = JSONResponse(content={"status": "success", "redirect_url": "/projects"})
    response.set_cookie(key="toast_message", value="Proyecto creado correctamente")
    return response

@router.get("/{id}/edit")
def edit_project_form(id: int, request: Request, db: Session = Depends(deps.get_db), user: User = Depends(deps.get_current_user)):
    if user.role != ADMIN:
        return RedirectResponse(url="/projects", status_code=status.HTTP_303_SEE_OTHER)

    project = db.query(Project).filter(Project.id == id).first()
    if not project:
        return RedirectResponse(url="/projects", status_code=status.HTTP_303_SEE_OTHER)
        
    clients = db.query(User).filter(User.role == CLIENT).all()
    workers = db.query(User).filter(User.role.in_([WORKER, SUPERVISOR])).all()
    account, roles = account_form_data(db, project)
    
    return templates.TemplateResponse("projects/form.html", {
        "request": request, 
        "user": user, 
        "project": project, 
        "clients": clients,
        "workers": workers,
        "account": account,
        "contact_roles": roles,
        "opportunity": None,
    })

@router.post("/{id}/edit")
def update_project(
    id: int,
    project_in: ProjectCreate,
    db: Session = Depends(deps.get_db),
    user: User = Depends(deps.get_current_user)
):
    if user.role != ADMIN:
        raise HTTPException(status_code=403, detail="Not authorized")

    project = db.query(Project).filter(Project.id == id).first()
    if not project:
         raise HTTPException(status_code=404, detail="Project not found")

    # Update Fields
    project.name = project_in.name
    project.province = project_in.province
    project.address = project_in.address
    project.waze_link = project_in.waze_link
    project.description = project_in.description
    project.is_active = project_in.is_active
    
    # Update Users
    all_ids = project_in.client_ids + project_in.worker_ids
    selected_users = db.query(User).filter(User.id.in_(all_ids)).all()
    project.users = selected_users

    # Client account and its contacts for this project (the old project_contacts are kept as history).
    apply_account(db, project, project_in)
    
    # Update Supplies (Replace All strategy for simplicity or nuanced?)
    # Simple strategy: Delete all old, add all new.
    db.query(ProjectSupply).filter(ProjectSupply.project_id == id).delete()
    for s in project_in.supplies:
        db.add(ProjectSupply(project_id=id, name=s.name, quantity=s.quantity))

    # Update Tasks
    db.query(ProjectTask).filter(ProjectTask.project_id == id).delete()
    for t in project_in.tasks:
        db.add(ProjectTask(project_id=id, description=t.description, is_required=t.is_required))

    # Update Locations
    db.query(ProjectLocation).filter(ProjectLocation.project_id == id).delete()
    for loc in project_in.locations:
        db.add(ProjectLocation(project_id=id, name=loc.name, location=loc.location, waze_pin=loc.waze_pin))

    # Update Budget
    import datetime
    budget = db.query(ProjectBudget).filter(ProjectBudget.project_id == id).first()
    if not budget:
        budget = ProjectBudget(project_id=id)
        db.add(budget)
    
    budget.licitation_number = project_in.licitation_number
    budget.contract_duration = project_in.contract_duration
    budget.is_prorrogable = project_in.is_prorrogable
    budget.active_prorogue = project_in.active_prorogue if project_in.is_prorrogable else False
    budget.prorrogable_time = project_in.prorrogable_time
    budget.prorrogable_amount = project_in.prorrogable_amount or 0.0
    
    if project_in.start_date:
        budget.start_date = datetime.datetime.strptime(project_in.start_date, "%Y-%m-%d").date()
    else:
        budget.start_date = None

    if project_in.end_date:
        budget.end_date = datetime.datetime.strptime(project_in.end_date, "%Y-%m-%d").date()
    else:
        budget.end_date = None
    
    db.flush() # Ensure budget.id if new

    # Update Lines (Delete and Recreate)
    db.query(BudgetLine).filter(BudgetLine.budget_id == budget.id).delete()
    for line in project_in.budget_lines:
        db.add(BudgetLine(
            budget_id=budget.id,
            name=line.name,
            subtotal=line.subtotal,
            tax_percentage=line.tax_percentage
        ))

    db.commit()
    
    # Audit Log
    try:
        log_activity(db, user=user, action="UPDATE", entity_type="PROJECT", entity_id=project.id, details=f"Actualizado proyecto {project.name}")
    except Exception as e:
        logger.error(f"Audit Log Error: {e}")
        
    response = JSONResponse(content={"status": "success", "redirect_url": "/projects"})
    response.set_cookie(key="toast_message", value="Proyecto actualizado correctamente")
    return response

@router.get("/{id}")
def get_project_detail(
    id: int, 
    request: Request, 
    page: int = 1,
    limit: int = 10,
    db: Session = Depends(deps.get_db), 
    user: User = Depends(deps.get_current_user)
):
    project = db.query(Project).filter(Project.id == id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    if user.role not in [ADMIN, SUPERVISOR] and user.id not in [u.id for u in project.users]:
        raise HTTPException(status_code=403, detail="Not authorized")

    # Financial Cost Integration
    manual_costs_query = db.query(func.sum(ProjectCost.amount)).filter(ProjectCost.project_id == project.id).scalar()
    manual_costs = manual_costs_query or 0.0

    payroll_costs = 0.0
    confirmed_schedules = db.query(ProjectSchedule).filter(
        ProjectSchedule.project_id == project.id,
        ProjectSchedule.is_confirmed == True
    ).all()

    for sched in confirmed_schedules:
        if sched.user and sched.user.hourly_rate:
            worker_rate = sched.user.hourly_rate
            regular_pay = sched.hours_worked * worker_rate
            overtime_pay = (sched.overtime_hours or 0.0) * worker_rate * 1.5
            company_cost = (regular_pay + overtime_pay) * 1.4467
            payroll_costs += company_cost

    total_costs = manual_costs + payroll_costs
    
    # Fetch manual project costs history
    project_costs_history = db.query(ProjectCost).filter(ProjectCost.project_id == project.id).order_by(ProjectCost.date.desc()).all()


    # Pagination for Logs
    offset = (page - 1) * limit
    logs_query = db.query(DailyLog).filter(DailyLog.project_id == id)
    total_records = logs_query.count()
    
    logs = logs_query.order_by(desc(DailyLog.date), desc(DailyLog.created_at))\
        .offset(offset)\
        .limit(limit)\
        .all()
        
    total_pages = ceil(total_records / limit)

    # Tree monitoring: admin/supervisor on any linked project, workers on their assigned ones
    # (the membership check above already applies to workers).
    monitoring_available = user.role in (ADMIN, SUPERVISOR, WORKER) and db.query(ReforestationProject.id).filter(
        ReforestationProject.project_id == project.id
    ).first() is not None

    return templates.TemplateResponse("projects/detail.html", {
        "monitoring_available": monitoring_available,
        "site_contacts": site_contacts(db, project),
        "account_id": project.account_id,
        "request": request, 
        "project": project, 
        "user": user,
        "logs": logs,
        "total_costs": total_costs,
        "project_costs_history": project_costs_history,
        "page": page,
        "total_pages": total_pages,
        "total_records": total_records
    })

@router.get("/{id}/logs")
def project_logs_redirect(id: int):
    return RedirectResponse(url=f"/logs?project_id={id}")
