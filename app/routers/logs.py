
import shutil
import uuid
import json
from pathlib import Path
from datetime import datetime, date
from typing import List, Optional

from fastapi import APIRouter, Depends, Form, File, UploadFile, status, Request, HTTPException
from fastapi.responses import RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from sqlalchemy import desc

from app.db.session import SessionLocal
from app.db.models.log import DailyLog, Photo
from app.db.models.project import Project
from app.db.models.log_task import DailyLogTask
from app.db.models.project_details import ProjectTask
from app.db.models.user import User
from app.db.models.associations import project_users
from app.routers import deps

router = APIRouter(
    prefix="/logs",
    tags=["logs"],
    dependencies=[Depends(deps.get_current_user)]
)

templates = Jinja2Templates(directory="app/templates")

@router.get("/")
async def list_logs(
    request: Request, 
    project_id: Optional[int] = None,
    db: Session = Depends(deps.get_db), 
    user: User = Depends(deps.get_current_user)
):
    # RBAC: Only Admin can access the global logs list
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="Not authorized")
        
    query = db.query(DailyLog).join(Project)
    
    # Filter by Project if provided
    if project_id:
        query = query.filter(DailyLog.project_id == project_id)
        
    logs = query.order_by(desc(DailyLog.date), desc(DailyLog.created_at)).all()
    
    # Get all projects for filter dropdown
    projects = db.query(Project).all()
    
    return templates.TemplateResponse("logs/list.html", {
        "request": request, 
        "logs": logs, 
        "user": user,
        "projects": projects,
        "selected_project_id": project_id
    })

@router.get("/{id}/detail")
async def get_log_detail(id: int, db: Session = Depends(deps.get_db), user: User = Depends(deps.get_current_user)):
    log = db.query(DailyLog).filter(DailyLog.id == id).first()
    if not log:
        raise HTTPException(status_code=404, detail="Log not found")
    
    # Auth check: Admin or Author
    if user.role != "admin" and log.user_id != user.id:
        raise HTTPException(status_code=403, detail="Not authorized")

    # Get all project tasks to allow editing (checking missed ones)
    all_project_tasks = log.project.tasks
    # Create a set of completed task IDs for O(1) lookup
    completed_task_ids = {entry.task_id for entry in log.task_entries}

    tasks_data = []
    for task in all_project_tasks:
        tasks_data.append({
            "task_id": task.id,
            "description": task.description,
            "completed": task.id in completed_task_ids,
            "is_required": task.is_required
        })

    return {
        "id": log.id,
        "project_name": log.project.name,
        "user_name": log.user.full_name or log.user.username,
        "date": log.date.strftime('%Y-%m-%d'),
        "notes": log.notes,
        "photos": [{"file_path": p.file_path} for p in log.photos],
        "created_at": log.created_at.isoformat() if log.created_at else None,
        "updated_at": log.updated_at.isoformat() if log.updated_at else None,
        "can_edit": (user.role == "admin" or log.user_id == user.id),
        "tasks": tasks_data
    }

@router.post("/{id}/delete")
async def delete_log(id: int, db: Session = Depends(deps.get_db), user: User = Depends(deps.get_current_user)):
    log = db.query(DailyLog).filter(DailyLog.id == id).first()
    if not log:
        raise HTTPException(status_code=404, detail="Log not found")

    if user.role != "admin" and log.user_id != user.id:
        raise HTTPException(status_code=403, detail="Not authorized")
    
    project_id = log.project_id
    # Cascade delete handles photos and task_entries if configured? 
    # daily_log_tasks model has no cascade defined explicitly on log relationship backref?
    # SQLAlchemy default cascade is usually not delete-orphan unless specified.
    # We added `cascade="all, delete-orphan"` to `photos` in Log model.
    # We should add it to `task_entries` in Log model ideally, or manually delete.
    # Let's check Log model... 
    # I'll manually delete for safety or trust SQLite FK if ON DELETE CASCADE (unlikely set).
    db.query(DailyLogTask).filter(DailyLogTask.log_id == id).delete()
    
    db.delete(log)
    db.commit()
    
    return RedirectResponse(url=f"/projects/{project_id}", status_code=status.HTTP_303_SEE_OTHER)

@router.post("/{id}/edit")
async def update_log(
    id: int,
    notes: str = Form(...),
    task_ids: List[int] = Form([], alias="tasks"),
    db: Session = Depends(deps.get_db),
    user: User = Depends(deps.get_current_user)
):
    log = db.query(DailyLog).filter(DailyLog.id == id).first()
    if not log:
        raise HTTPException(status_code=404, detail="Log not found")

    if user.role != "admin" and log.user_id != user.id:
        raise HTTPException(status_code=403, detail="Not authorized")
    
    log.notes = notes
    
    # Update tasks
    # Clear existing tasks? Or merge?
    # Usually easier to clear and re-add for checklist behavior
    db.query(DailyLogTask).filter(DailyLogTask.log_id == id).delete()
    
    for t_id in task_ids:
        db.add(DailyLogTask(log_id=log.id, task_id=t_id, completed=True))

    db.commit()
    return RedirectResponse(url=f"/projects/{log.project_id}", status_code=status.HTTP_303_SEE_OTHER)

@router.get("/new")
async def new_log_form(request: Request, project_id: Optional[int] = None, db: Session = Depends(deps.get_db), user: User = Depends(deps.get_current_user)):
    # RBAC: Clients cannot report
    if user.role == "client":
        return RedirectResponse(url="/projects", status_code=status.HTTP_303_SEE_OTHER)

    # Get available projects
    if user.role == "admin":
        projects = db.query(Project).filter(Project.is_active == True).all()
    else:
        # Worker: only assigned active projects
        # Explicit query to avoid DetachedInstanceError with lazy loading
        projects = db.query(Project)\
            .join(project_users)\
            .filter(project_users.c.user_id == user.id)\
            .filter(Project.is_active == True)\
            .all()

    # Pre-fetch tasks for all available projects to pass to JS
    project_tasks_map = {}
    for p in projects:
        project_tasks_map[p.id] = [
            {"id": t.id, "description": t.description, "is_required": t.is_required} 
            for t in p.tasks
        ]

    today = date.today()
    project_tasks_json = json.dumps(project_tasks_map)
    
    return templates.TemplateResponse("logs/form.html", {
        "request": request,
        "user": user, 
        "projects": projects,
        "today": today,
        "project_tasks_json": project_tasks_json,
        "selected_project_id": project_id,
        "project_tasks_json": json.dumps(project_tasks_map)
    })

@router.post("/new")
async def create_log(
    project_id: int = Form(...),
    date_val: str = Form(..., alias="date"),
    notes: str = Form(""),
    task_ids: List[int] = Form([], alias="tasks"), # IDs of completed tasks
    photos: List[UploadFile] = File(default=None),
    db: Session = Depends(deps.get_db),
    user: User = Depends(deps.get_current_user)
):
    if user.role == "client":
         return RedirectResponse(url="/projects", status_code=status.HTTP_303_SEE_OTHER)
    
    # Validation
    if user.role != "admin":
        assigned = db.query(Project).filter(Project.id == project_id, Project.users.any(id=user.id)).first()
        if not assigned:
             return RedirectResponse(url="/projects?error=access_denied", status_code=status.HTTP_303_SEE_OTHER)

    # Create Log
    log_date = datetime.strptime(date_val, "%Y-%m-%d").date()
    new_log = DailyLog(
        project_id=project_id,
        user_id=user.id,
        date=log_date,
        notes=notes
    )
    db.add(new_log)
    db.flush() # Get ID

    # Handle Tasks
    if task_ids:
        # We only get IDs of CHECKED tasks (completed=True)
        # Should we save unchecked tasks as completed=False? 
        # Requirement: "Checkbox list... attach to create report". 
        # Storing only completed ones is efficient, but if we want to show "Missed tasks" later, we might want all.
        # For now, let's store all tasks for the project? Or just the ones submitted?
        # Usually easier to just store relevant ones. Let's start with just storing completed ones for history.
        for t_id in task_ids:
            db.add(DailyLogTask(log_id=new_log.id, task_id=t_id, completed=True))

    # Handle Photos
    if photos:
        upload_dir = Path("app/static/uploads")
        year_month = log_date.strftime("%Y/%m")
        target_dir = upload_dir / year_month
        target_dir.mkdir(parents=True, exist_ok=True)

        for photo in photos:
            if photo.filename:
                ext = photo.filename.split(".")[-1]
                unique_name = f"{uuid.uuid4()}.{ext}"
                file_path = target_dir / unique_name
                
                with open(file_path, "wb") as buffer:
                    shutil.copyfileobj(photo.file, buffer)
                
                relative_path = f"/static/uploads/{year_month}/{unique_name}"
                db_photo = Photo(log_id=new_log.id, file_path=relative_path)
                db.add(db_photo)

    db.commit()
    return RedirectResponse(url=f"/projects/{project_id}", status_code=status.HTTP_303_SEE_OTHER)
