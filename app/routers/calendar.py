
from typing import List, Optional
from datetime import datetime, date
from fastapi import APIRouter, Depends, Form, Request, status, HTTPException
from fastapi.responses import RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.db.models.schedule import ProjectSchedule, ScheduleTask
from app.db.models.project import Project
from app.db.models.user import User
from app.routers import deps

router = APIRouter(
    prefix="/calendar",
    tags=["calendar"],
    dependencies=[Depends(deps.get_current_user)]
)

templates = Jinja2Templates(directory="app/templates")

@router.get("/")
async def calendar_view(request: Request, db: Session = Depends(deps.get_db), user: User = Depends(deps.get_current_user)):
    if user.role == "client":
        return RedirectResponse(url="/projects", status_code=status.HTTP_303_SEE_OTHER)

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
async def get_events(start: str, end: str, db: Session = Depends(deps.get_db), user: User = Depends(deps.get_current_user)):
    query = db.query(ProjectSchedule)
    
    if user.role != "admin":
        query = query.filter(ProjectSchedule.user_id == user.id)
    
    schedules = query.filter(ProjectSchedule.date >= start, ProjectSchedule.date <= end).all()
    
    events = []
    for s in schedules:
        evt = {
            "id": s.id,
            "title": f"{s.project.name} ({s.user.username})",
            "start": s.date.isoformat(),
            # Workers click to go to project, Admins click to Edit (handled in JS)
            "url": f"/projects/{s.project.id}" if user.role != "admin" else None, 
            "extendedProps": {
                "worker_id": s.user_id,
                "project_id": s.project_id,
                "project_name": s.project.name,
                "project_name": s.project.name,
                "worker_name": s.user.full_name or s.user.username,
                "tasks": [{"id": t.id, "description": t.description} for t in s.tasks]
            },
            "color": "#000000" if user.role == "admin" else "#2563eb"
        }
        events.append(evt)
        
    return JSONResponse(events)

@router.post("/schedule")
async def create_schedule(
    project_id: int = Form(...),
    user_id: int = Form(...),
    date_val: str = Form(..., alias="date"),
    tasks: List[str] = Form([], alias="tasks"),
    db: Session = Depends(deps.get_db),
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
    db.flush()
    
    # Save manual tasks
    for task_desc in tasks:
        if task_desc.strip():
            db.add(ScheduleTask(schedule_id=new_schedule.id, description=task_desc.strip()))

    db.commit()
    
    return JSONResponse({"status": "success", "message": "Asignación creada correctamente"})

@router.post("/schedule/{id}/delete")
async def delete_schedule(id: int, db: Session = Depends(deps.get_db), user: User = Depends(deps.get_current_user)):
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="Not authorized")
    
    schedule = db.query(ProjectSchedule).filter(ProjectSchedule.id == id).first()
    if not schedule:
        return JSONResponse({"status": "error", "message": "Asignación no encontrada"}, status_code=404)
        
    db.delete(schedule)
    db.commit()
    return JSONResponse({"status": "success", "message": "Asignación eliminada correctamente"})

@router.post("/schedule/{id}/edit")
async def update_schedule(
    id: int,
    project_id: int = Form(...),
    user_id: int = Form(...),
    date_val: str = Form(..., alias="date"),
    tasks: List[str] = Form([], alias="tasks"),
    db: Session = Depends(deps.get_db),
    user: User = Depends(deps.get_current_user)
):
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="Not authorized")

    schedule = db.query(ProjectSchedule).filter(ProjectSchedule.id == id).first()
    if not schedule:
        return JSONResponse({"status": "error", "message": "Asignación no encontrada"}, status_code=404)
    
    schedule.project_id = project_id
    schedule.user_id = user_id
    schedule.date = datetime.strptime(date_val, "%Y-%m-%d").date()
    
    # Update tasks (Replace all)
    db.query(ScheduleTask).filter(ScheduleTask.schedule_id == id).delete()
    for task_desc in tasks:
        if task_desc.strip():
            db.add(ScheduleTask(schedule_id=schedule.id, description=task_desc.strip()))

    db.commit()
    return JSONResponse({"status": "success", "message": "Asignación actualizada correctamente"})
