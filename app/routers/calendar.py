
from typing import List, Optional
from datetime import datetime, date
from fastapi import APIRouter, Depends, Form, Request, status, HTTPException
from fastapi.responses import RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.db.models.schedule import ProjectSchedule
from app.db.models.project import Project
from app.db.models.user import User
from app.routers import deps

router = APIRouter(
    prefix="/calendar",
    tags=["calendar"],
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
async def calendar_view(request: Request, db: Session = Depends(get_db), user: User = Depends(deps.get_current_user)):
    # Workers and Admins can see calendar
    # Clients? Unspecified in prompt, but let's hide or show read-only. 
    # Prompt said "admin and worker".
    if user.role == "client":
        return RedirectResponse(url="/projects", status_code=status.HTTP_303_SEE_OTHER)

    # For Schedule Modal
    projects = []
    workers = []
    if user.role == "admin":
        projects = db.query(Project).filter(Project.is_active == True).all()
        workers = db.query(User).filter(User.role == "worker").all()

    return templates.TemplateResponse("calendar/index.html", {
        "request": request, 
        "user": user,
        "projects": projects,
        "workers": workers
    })

@router.get("/events")
async def get_events(start: str, end: str, db: Session = Depends(get_db), user: User = Depends(deps.get_current_user)):
    # FullCalendar passes start/end dates
    # start_date = datetime.fromisoformat(start).date() # simplified
    
    query = db.query(ProjectSchedule)
    
    # Workers see only their assignments
    if user.role != "admin":
        query = query.filter(ProjectSchedule.user_id == user.id)
    
    schedules = query.filter(ProjectSchedule.date >= start, ProjectSchedule.date <= end).all()
    
    events = []
    for s in schedules:
        events.append({
            "id": s.id,
            "title": f"{s.project.name} ({s.user.username})",
            "start": s.date.isoformat(),
            "url": f"/projects/{s.project.id}",  # Clicking takes to project
            "extendedProps": {
                "worker": s.user.username,
                "project": s.project.name
            },
            "color": "#000000" if user.role == "admin" else "#2563eb" # Black for admin, Blue for worker
        })
        
    return JSONResponse(events)

@router.post("/schedule")
async def create_schedule(
    project_id: int = Form(...),
    user_id: int = Form(...),
    date_val: str = Form(..., alias="date"),
    db: Session = Depends(get_db),
    user: User = Depends(deps.get_current_user)
):
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="Not authorized")
        
    new_schedule = ProjectSchedule(
        project_id=project_id,
        user_id=user_id,
        date=datetime.strptime(date_val, "%Y-%m-%d").date()
    )
    db.add(new_schedule)
    db.commit()
    
    return RedirectResponse(url="/calendar", status_code=status.HTTP_303_SEE_OTHER)
