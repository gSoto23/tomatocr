
import json
from typing import List, Optional
from fastapi import APIRouter, Depends, Form, Request, status, HTTPException, Body
from fastapi.responses import RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from pydantic import BaseModel

from app.db.session import SessionLocal
from app.db.models.project import Project
from app.db.models.project_details import ProjectSupply, ProjectTask, ProjectContact
from app.db.models.finance import ProjectBudget, BudgetLine
from app.db.models.user import User
from app.db.models.user import User
from app.db.models.log import DailyLog
from app.db.models.associations import project_users
from sqlalchemy import desc, func
from math import ceil
from app.routers import deps

router = APIRouter(
    prefix="/projects",
    tags=["projects"],
    dependencies=[Depends(deps.get_current_user)]
)

from app.core.templates import templates

# Pydantic Models for JSON body
class SupplyCreate(BaseModel):
    name: str
    quantity: str

class TaskCreate(BaseModel):
    description: str
    is_required: bool = True

class ContactCreate(BaseModel):
    name: str
    phone: Optional[str] = None
    email: Optional[str] = None
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
    # Lists
    contacts: List[ContactCreate] = []
    supplies: List[SupplyCreate] = []
    tasks: List[TaskCreate] = []
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
async def list_projects(
    request: Request, 
    page: int = 1, 
    limit: int = 10,
    db: Session = Depends(deps.get_db), 
    user: User = Depends(deps.get_current_user)
):
    offset = (page - 1) * limit
    
    if user.role == "admin":
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

@router.get("/new")
async def new_project_form(request: Request, db: Session = Depends(deps.get_db), user: User = Depends(deps.get_current_user)):
    if user.role != "admin": 
        return RedirectResponse(url="/projects", status_code=status.HTTP_303_SEE_OTHER)

    clients = db.query(User).filter(User.role == "client").all()
    workers = db.query(User).filter(User.role == "worker").all()
    
    return templates.TemplateResponse("projects/form.html", {
        "request": request, 
        "user": user, 
        "project": None, 
        "clients": clients,
        "workers": workers
    })

@router.post("/new")
async def create_project(
    project_in: ProjectCreate,
    db: Session = Depends(deps.get_db),
    user: User = Depends(deps.get_current_user)
):
    if user.role != "admin":
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

    # Add Contacts
    for c in project_in.contacts:
        db.add(ProjectContact(
            project_id=project.id, 
            name=c.name, 
            phone=c.phone, 
            email=c.email, 
            position=c.position
        ))

    # Add Supplies
    for s in project_in.supplies:
        db.add(ProjectSupply(project_id=project.id, name=s.name, quantity=s.quantity))

    # Add Tasks
    for t in project_in.tasks:
        db.add(ProjectTask(project_id=project.id, description=t.description, is_required=t.is_required))

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
    # Return JSON redirect instruction with Toast Cookie
    response = JSONResponse(content={"status": "success", "redirect_url": "/projects"})
    response.set_cookie(key="toast_message", value="Proyecto creado correctamente")
    return response

@router.get("/{id}/edit")
async def edit_project_form(id: int, request: Request, db: Session = Depends(deps.get_db), user: User = Depends(deps.get_current_user)):
    if user.role != "admin":
        return RedirectResponse(url="/projects", status_code=status.HTTP_303_SEE_OTHER)

    project = db.query(Project).filter(Project.id == id).first()
    if not project:
        return RedirectResponse(url="/projects", status_code=status.HTTP_303_SEE_OTHER)
        
    clients = db.query(User).filter(User.role == "client").all()
    workers = db.query(User).filter(User.role == "worker").all()
    
    return templates.TemplateResponse("projects/form.html", {
        "request": request, 
        "user": user, 
        "project": project,
        "clients": clients,
        "workers": workers
    })

@router.post("/{id}/edit")
async def update_project(
    id: int,
    project_in: ProjectCreate,
    db: Session = Depends(deps.get_db),
    user: User = Depends(deps.get_current_user)
):
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="Not authorized")

    project = db.query(Project).filter(Project.id == id).first()
    if not project:
         raise HTTPException(status_code=404, detail="Project not found")

    # Update Fields
    project.name = project_in.name
    project.client_display_name = project_in.client_display_name
    project.province = project_in.province
    project.address = project_in.address
    project.waze_link = project_in.waze_link
    project.description = project_in.description
    project.is_active = project_in.is_active
    
    # Update Users
    all_ids = project_in.client_ids + project_in.worker_ids
    selected_users = db.query(User).filter(User.id.in_(all_ids)).all()
    project.users = selected_users

    # Update Contacts
    db.query(ProjectContact).filter(ProjectContact.project_id == id).delete()
    for c in project_in.contacts:
        db.add(ProjectContact(
            project_id=id, 
            name=c.name, 
            phone=c.phone, 
            email=c.email, 
            position=c.position
        ))
    
    # Update Supplies (Replace All strategy for simplicity or nuanced?)
    # Simple strategy: Delete all old, add all new.
    db.query(ProjectSupply).filter(ProjectSupply.project_id == id).delete()
    for s in project_in.supplies:
        db.add(ProjectSupply(project_id=id, name=s.name, quantity=s.quantity))

    # Update Tasks
    db.query(ProjectTask).filter(ProjectTask.project_id == id).delete()
    for t in project_in.tasks:
        db.add(ProjectTask(project_id=id, description=t.description, is_required=t.is_required))

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
    response = JSONResponse(content={"status": "success", "redirect_url": "/projects"})
    response.set_cookie(key="toast_message", value="Proyecto actualizado correctamente")
    return response

@router.get("/{id}")
async def get_project_detail(
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

    if user.role != "admin" and user.id not in [u.id for u in project.users]:
        raise HTTPException(status_code=403, detail="Not authorized")

    # Pagination for Logs
    offset = (page - 1) * limit
    logs_query = db.query(DailyLog).filter(DailyLog.project_id == id)
    total_records = logs_query.count()
    
    logs = logs_query.order_by(desc(DailyLog.date), desc(DailyLog.created_at))\
        .offset(offset)\
        .limit(limit)\
        .all()
        
    total_pages = ceil(total_records / limit)

    return templates.TemplateResponse("projects/detail.html", {
        "request": request, 
        "project": project, 
        "user": user,
        "logs": logs,
        "page": page,
        "total_pages": total_pages,
        "total_records": total_records
    })

@router.get("/{id}/logs")
async def project_logs_redirect(id: int):
    return RedirectResponse(url=f"/logs?project_id={id}")
