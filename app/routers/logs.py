
import shutil
import uuid
from pathlib import Path
from datetime import datetime, date
from typing import List, Optional

from fastapi import APIRouter, Depends, Form, File, UploadFile, status, Request, HTTPException
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from sqlalchemy import desc

from app.db.session import SessionLocal
from app.db.models.log import DailyLog, Photo
from app.db.models.project import Project
from app.db.models.user import User
from app.routers import deps

router = APIRouter(
    prefix="/logs",
    tags=["logs"],
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
async def list_logs(
    request: Request, 
    project_id: Optional[int] = None,
    db: Session = Depends(get_db), 
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

@router.get("/new")
async def new_log_form(request: Request, project_id: Optional[int] = None, db: Session = Depends(get_db), user: User = Depends(deps.get_current_user)):
    # RBAC: Clients cannot report
    if user.role == "client":
        return RedirectResponse(url="/projects", status_code=status.HTTP_303_SEE_OTHER)

    # Get available projects
    if user.role == "admin":
        projects = db.query(Project).filter(Project.is_active == True).all()
    else:
        # Worker: only assigned active projects
        projects = [p for p in user.projects if p.is_active]

    today = date.today()
    return templates.TemplateResponse("logs/form.html", {
        "request": request,
        "user": user, 
        "projects": projects,
        "today": today,
        "selected_project_id": project_id
    })

@router.post("/new")
async def create_log(
    project_id: int = Form(...),
    date_val: str = Form(..., alias="date"),
    notes: str = Form(""),
    photos: List[UploadFile] = File(default=None),
    db: Session = Depends(get_db),
    user: User = Depends(deps.get_current_user)
):
    if user.role == "client":
         return RedirectResponse(url="/projects", status_code=status.HTTP_303_SEE_OTHER)
    
    # Validation: Ensure user is assigned to project (if not admin)
    if user.role != "admin":
        # Check assignment
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
    db.flush()

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
    # Redirect to Project Detail instead of global log list
    return RedirectResponse(url=f"/projects/{project_id}", status_code=status.HTTP_303_SEE_OTHER)
