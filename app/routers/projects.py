
from typing import List, Optional
from fastapi import APIRouter, Depends, Form, Request, status, HTTPException
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.db.models.project import Project
from app.db.models.user import User
from app.routers import deps

router = APIRouter(
    prefix="/projects",
    tags=["projects"],
    dependencies=[Depends(deps.get_current_user)]
)

templates = Jinja2Templates(directory="app/templates")

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@router.get("/")
async def list_projects(request: Request, db: Session = Depends(get_db), user: User = Depends(deps.get_current_user)):
    if user.role == "admin":
        projects = db.query(Project).all()
    else:
        # Worker/Client sees only assigned projects
        # Since we set up back_populates="projects" in User, we can access user.projects
        projects = user.projects
        
    return templates.TemplateResponse("projects/list.html", {"request": request, "projects": projects, "user": user})

@router.get("/new")
async def new_project_form(request: Request, db: Session = Depends(get_db), user: User = Depends(deps.get_current_user)):
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
    name: str = Form(...),
    client_ids: List[int] = Form([]),
    worker_ids: List[int] = Form([]),
    location: Optional[str] = Form(None),
    description: Optional[str] = Form(None),
    db: Session = Depends(get_db),
    user: User = Depends(deps.get_current_user)
):
    if user.role != "admin":
         return RedirectResponse(url="/projects", status_code=status.HTTP_303_SEE_OTHER)

    project = Project(
        name=name,
        location=location,
        description=description
    )
    
    # Assign users
    all_ids = client_ids + worker_ids
    if all_ids:
        selected_users = db.query(User).filter(User.id.in_(all_ids)).all()
        project.users = selected_users

    db.add(project)
    db.commit()
    return RedirectResponse(url="/projects", status_code=status.HTTP_303_SEE_OTHER)

@router.get("/{id}/edit")
async def edit_project_form(id: int, request: Request, db: Session = Depends(get_db), user: User = Depends(deps.get_current_user)):
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
    name: str = Form(...),
    client_ids: List[int] = Form([]),
    worker_ids: List[int] = Form([]),
    location: Optional[str] = Form(None),
    description: Optional[str] = Form(None),
    is_active: bool = Form(False),
    db: Session = Depends(get_db),
    user: User = Depends(deps.get_current_user)
):
    if user.role != "admin":
        return RedirectResponse(url="/projects", status_code=status.HTTP_303_SEE_OTHER)

    project = db.query(Project).filter(Project.id == id).first()
    if project:
        project.name = name
        project.location = location
        project.description = description
        project.is_active = is_active
        
        # Update users
        all_ids = client_ids + worker_ids
        # Clear current and re-add? Or specific logic?
        # Simplest is find all new selected and replace list
        selected_users = db.query(User).filter(User.id.in_(all_ids)).all()
        project.users = selected_users
        
        db.commit()
    return RedirectResponse(url="/projects", status_code=status.HTTP_303_SEE_OTHER)

@router.get("/{id}")
async def get_project_detail(
    id: int, 
    request: Request, 
    db: Session = Depends(get_db), 
    user: User = Depends(deps.get_current_user)
):
    project = db.query(Project).filter(Project.id == id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    # Auth check: Admin or Assigned User
    if user.role != "admin" and user.id not in [u.id for u in project.users]:
        raise HTTPException(status_code=403, detail="Not authorized")

    # Fetch recent logs for this project
    # We need to import DailyLog inside or top-level. 
    # Doing inline to verify import availability or use relationship if exists (project.logs)
    logs = sorted(project.logs, key=lambda x: (x.date, x.created_at), reverse=True)

    return templates.TemplateResponse("projects/detail.html", {
        "request": request, 
        "project": project, 
        "user": user,
        "logs": logs
    })
