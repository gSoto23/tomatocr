
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

from app.core.templates import templates

@router.get("/")
async def calendar_view(request: Request, db: Session = Depends(deps.get_db), user: User = Depends(deps.get_current_user)):
    # Supervisor sees admin view (can manage), Worker sees their own calendar
    # Client is redirected
    if user.role == "client":
        return RedirectResponse(url="/projects", status_code=status.HTTP_303_SEE_OTHER)

    projects = []
    workers = []
    # Admin and Supervisor get full list
    if user.role in ["admin", "supervisor"]:
        projects = db.query(Project).filter(Project.is_active == True).all()
        workers = db.query(User).filter(User.role.in_(["worker", "supervisor"])).all()

    return templates.TemplateResponse("calendar/index.html", {
        "request": request, 
        "user": user,
        "projects": projects,
        "workers": workers
    })

@router.get("/events")
async def get_events(start: str, end: str, db: Session = Depends(deps.get_db), user: User = Depends(deps.get_current_user)):
    query = db.query(ProjectSchedule)
    
    # Admin and Supervisor see all
    if user.role not in ["admin", "supervisor"]:
        query = query.filter(ProjectSchedule.user_id == user.id)
    
    schedules = query.filter(ProjectSchedule.date >= start, ProjectSchedule.date <= end).all()
    
    events = []
    for s in schedules:
        if not s.user or not s.project:
            continue
            
        is_manager = user.role in ["admin", "supervisor"]
        evt = {
            "id": s.id,
            "title": f"{s.project.name} ({s.user.username})",
            "start": s.date.isoformat(),
            # Workers click to go to project, Managers click to Edit (handled in JS)
            "url": f"/projects/{s.project.id}" if not is_manager else None, 
            "extendedProps": {
                "worker_id": s.user_id,
                "project_id": s.project_id,
                "project_name": s.project.name,
                "worker_name": s.user.full_name or s.user.username,
                "tasks": [{"id": t.id, "title": t.title, "description": t.description, "completed": t.completed} for t in s.tasks]
            },
            "color": "#000000" if is_manager else "#2563eb"
        }
        events.append(evt)
        
    return JSONResponse(events)

@router.post("/schedule")
async def create_schedule(
    project_id: int = Form(...),
    user_id: int = Form(...),
    date_val: str = Form(..., alias="date"),
    tasks_json: str = Form("[]"),
    db: Session = Depends(deps.get_db),
    user: User = Depends(deps.get_current_user)
):
    if user.role not in ["admin", "supervisor"]:
        raise HTTPException(status_code=403, detail="Not authorized")
        
    new_schedule = ProjectSchedule(
        project_id=project_id,
        user_id=user_id,
        date=datetime.strptime(date_val, "%Y-%m-%d").date()
    )
    db.add(new_schedule)
    db.flush()
    
    # Save manual tasks
    import json
    try:
        tasks_data = json.loads(tasks_json)
        for task in tasks_data:
            title = task.get("title", "")
            desc = task.get("description", "")
            if title.strip() or desc.strip():
                db.add(ScheduleTask(
                    schedule_id=new_schedule.id, 
                    title=title.strip(),
                    description=desc.strip()
                ))
    except json.JSONDecodeError:
        pass # Handle error or ignore

    db.commit()
    
    return JSONResponse({"status": "success", "message": "Asignación creada correctamente"})

@router.post("/schedule/{id}/delete")
async def delete_schedule(id: int, db: Session = Depends(deps.get_db), user: User = Depends(deps.get_current_user)):
    if user.role not in ["admin", "supervisor"]:
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
    tasks_json: str = Form("[]"),
    db: Session = Depends(deps.get_db),
    user: User = Depends(deps.get_current_user)
):
    if user.role not in ["admin", "supervisor"]:
        raise HTTPException(status_code=403, detail="Not authorized")

    schedule = db.query(ProjectSchedule).filter(ProjectSchedule.id == id).first()
    if not schedule:
        return JSONResponse({"status": "error", "message": "Asignación no encontrada"}, status_code=404)
    
    schedule.project_id = project_id
    schedule.user_id = user_id
    schedule.date = datetime.strptime(date_val, "%Y-%m-%d").date()
    
    # Update tasks (Replace all)
    db.query(ScheduleTask).filter(ScheduleTask.schedule_id == id).delete()
    
    import json
    try:
        tasks_data = json.loads(tasks_json)
        for task in tasks_data:
            title = task.get("title", "")
            desc = task.get("description", "")
            if title.strip() or desc.strip():
                db.add(ScheduleTask(
                    schedule_id=schedule.id, 
                    title=title.strip(),
                    description=desc.strip()
                ))
    except json.JSONDecodeError:
        pass

    db.commit()
    return JSONResponse({"status": "success", "message": "Asignación actualizada correctamente"})

@router.post("/task/{id}/toggle")
async def toggle_task_status(id: int, db: Session = Depends(deps.get_db), user: User = Depends(deps.get_current_user)):
    task = db.query(ScheduleTask).filter(ScheduleTask.id == id).first()
    if not task:
        return JSONResponse({"status": "error", "message": "Tarea no encontrada"}, status_code=404)
    
    # Check authorization: Admin, Supervisor, or the assigned worker
    if user.role not in ["admin", "supervisor"] and task.schedule.user_id != user.id:
         raise HTTPException(status_code=403, detail="Not authorized")

    task.completed = not task.completed
    db.commit()
    
    return JSONResponse({
        "status": "success", 
        "message": "Estado actualizado", 
        "completed": task.completed
    })
