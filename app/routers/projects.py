
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
from app.db.models.user import User
from app.db.models.associations import project_users
from app.routers import deps

router = APIRouter(
    prefix="/projects",
    tags=["projects"],
    dependencies=[Depends(deps.get_current_user)]
)

templates = Jinja2Templates(directory="app/templates")

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

@router.get("/")
async def list_projects(request: Request, db: Session = Depends(deps.get_db), user: User = Depends(deps.get_current_user)):
    if user.role == "admin":
        projects = db.query(Project).all()
    else:
        # Explicit query
        projects = db.query(Project)\
            .join(project_users)\
            .filter(project_users.c.user_id == user.id)\
            .all()   
    return templates.TemplateResponse("projects/list.html", {"request": request, "projects": projects, "user": user})

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

    db.commit()
    # Return JSON redirect instruction
    return {"status": "success", "redirect_url": "/projects"}

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

    db.commit()
    return {"status": "success", "redirect_url": "/projects"}

@router.get("/{id}")
async def get_project_detail(
    id: int, 
    request: Request, 
    db: Session = Depends(deps.get_db), 
    user: User = Depends(deps.get_current_user)
):
    project = db.query(Project).filter(Project.id == id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    if user.role != "admin" and user.id not in [u.id for u in project.users]:
        raise HTTPException(status_code=403, detail="Not authorized")

    logs = sorted(project.logs, key=lambda x: (x.date, x.created_at), reverse=True)

    return templates.TemplateResponse("projects/detail.html", {
        "request": request, 
        "project": project, 
        "user": user,
        "logs": logs
    })
