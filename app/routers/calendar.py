
from typing import Optional
from datetime import datetime
from fastapi import APIRouter, Depends, Form, Request, status, HTTPException
from fastapi.responses import RedirectResponse, JSONResponse
from sqlalchemy.orm import Session

from app.db.models.schedule import ProjectSchedule, ScheduleTask
from app.db.models.project import Project
from app.db.models.project_details import ProjectLocation
from app.db.models.user import User
from app.routers import deps
from app.core.roles import ADMIN, CLIENT, OPERATIONS_ROLES, SUPERVISOR, WORKER

router = APIRouter(
    prefix="/calendar",
    tags=["calendar"],
    dependencies=[Depends(deps.require_roles(*OPERATIONS_ROLES))]
)

from app.core.templates import templates
from app.utils.activity import log_activity

@router.get("/")
def calendar_view(request: Request, db: Session = Depends(deps.get_db), user: User = Depends(deps.get_current_user)):
    # Supervisor sees admin view (can manage), Worker sees their own calendar
    # Client is redirected
    if user.role == CLIENT:
        return RedirectResponse(url="/projects", status_code=status.HTTP_303_SEE_OTHER)

    projects = []
    workers = []
    # Admin and Supervisor get full list
    locations = {}
    if user.role in [ADMIN, SUPERVISOR]:
        projects = db.query(Project).filter(Project.is_active == True).order_by(Project.name).all()
        # Only people who can still work (not deactivated or liquidated).
        workers = [w for w in db.query(User).filter(User.role.in_([WORKER, SUPERVISOR])).order_by(User.full_name)
                   if deps.can_log_in(w)]
        locations = {p.id: [{"id": l.id, "name": l.name} for l in p.locations if l.archived_at is None]
                     for p in projects}

    return templates.TemplateResponse("calendar/index.html", {
        "request": request, 
        "user": user,
        "projects": projects,
        "workers": workers,
        "locations": locations,
    })

@router.get("/events")
def get_events(start: str, end: str, db: Session = Depends(deps.get_db), user: User = Depends(deps.get_current_user)):
    query = db.query(ProjectSchedule)
    
    # Admin and Supervisor see all
    if user.role not in [ADMIN, SUPERVISOR]:
        query = query.filter(ProjectSchedule.user_id == user.id)
    
    schedules = query.filter(ProjectSchedule.date >= start, ProjectSchedule.date <= end).all()
    group_sizes = {}
    if user.role in [ADMIN, SUPERVISOR]:
        keys = {group_key(s) for s in schedules}
        for key in keys:
            group_sizes[key] = group_query(db, *key).count()

    events = []
    for s in schedules:
        if not s.user or not s.project:
            continue
            
        is_manager = user.role in [ADMIN, SUPERVISOR]
        evt = {
            "id": s.id,
            "title": f"{s.project.name} ({s.user.full_name or s.user.username})",
            "start": s.date.isoformat(),
            # Workers click to go to project, Managers click to Edit (handled in JS)
            "url": f"/projects/{s.project.id}" if not is_manager else None, 
            "extendedProps": {
                "worker_id": s.user_id,
                "project_id": s.project_id,
                "project_name": s.project.name,
                "worker_name": s.user.full_name or s.user.username,
                "location_id": s.location_id,
                "location_name": s.location.name if s.location else None,
                "hours": s.hours_worked,
                "group_size": group_sizes.get(group_key(s), 1),
                "tasks": [{"id": t.id, "title": t.title, "description": t.description, "completed": t.completed} for t in s.tasks]
            },
            "color": "#000000" if is_manager else "#2563eb"
        }
        events.append(evt)
        
    return JSONResponse(events)

def group_key(schedule: ProjectSchedule):
    """Assignments made together (one date range) share project, person and creation time."""
    return (schedule.project_id, schedule.user_id, schedule.created_at)


def group_query(db: Session, project_id: int, user_id: int, created_at):
    return db.query(ProjectSchedule).filter(ProjectSchedule.project_id == project_id,
                                            ProjectSchedule.user_id == user_id,
                                            ProjectSchedule.created_at == created_at)


def schedules_in_scope(db: Session, schedule: ProjectSchedule, scope: str) -> list:
    if scope == "group" and schedule.created_at is not None:
        return group_query(db, *group_key(schedule)).order_by(ProjectSchedule.date).all()
    return [schedule]


def apply_tasks(db: Session, schedule: ProjectSchedule, tasks_data, by_id: bool = True):
    """Updates tasks in place: an edited or unchanged task keeps whether the worker ticked it."""
    existing = {t.id: t for t in db.query(ScheduleTask).filter(ScheduleTask.schedule_id == schedule.id)}
    kept = set()
    for task in tasks_data if isinstance(tasks_data, list) else []:
        title = str(task.get("title") or "").strip()[:100]
        desc = str(task.get("description") or "").strip()[:255]
        if not (title or desc):
            continue
        row = existing.get(task.get("id")) if by_id and isinstance(task.get("id"), int) else None
        if row is None:  # other days of the range, or callers without ids: same title and description
            row = next((t for t in existing.values() if t.id not in kept
                        and (t.title or "") == title and (t.description or "") == desc), None)
        if row is None:
            db.add(ScheduleTask(schedule_id=schedule.id, title=title, description=desc))
        else:
            row.title, row.description = title, desc
            kept.add(row.id)
    for task_id, row in existing.items():
        if task_id not in kept:
            db.delete(row)


def check_location(db: Session, project_id: int, location_id: Optional[int]) -> Optional[int]:
    """The sede must belong to the project; anything else means "no sede"."""
    if not location_id:
        return None
    ok = db.query(ProjectLocation.id).filter(ProjectLocation.id == location_id,
                                             ProjectLocation.project_id == project_id).first()
    return location_id if ok else None


def conflicts(db: Session, user_id: int, days, exclude_id: Optional[int] = None) -> list:
    """Other assignments of this person on those days (any project)."""
    query = db.query(ProjectSchedule).filter(ProjectSchedule.user_id == user_id, ProjectSchedule.date.in_(list(days)))
    if exclude_id:
        query = query.filter(ProjectSchedule.id != exclude_id)
    return query.order_by(ProjectSchedule.date).all()


def conflict_response(found: list):
    listed = ", ".join(f"{s.date:%d/%m} ({s.project.name if s.project else '?'})" for s in found[:5])
    more = f" y {len(found) - 5} más" if len(found) > 5 else ""
    return JSONResponse({"status": "conflict", "message": f"Esa persona ya tiene asignación el {listed}{more}. "
                         "¿Asignarla igual?"}, status_code=409)


def person_name(db: Session, user_id: int) -> str:
    person = db.get(User, user_id)
    return (person.full_name or person.username) if person else f"usuario {user_id}"


def project_name(db: Session, project_id: int) -> str:
    project = db.get(Project, project_id)
    return project.name if project else f"proyecto {project_id}"


@router.post("/schedule")
def create_schedule(
    project_id: int = Form(...),
    user_id: int = Form(...),
    date_val: str = Form(..., alias="date"),
    end_date: Optional[str] = Form(None),
    tasks_json: str = Form("[]"),
    location_id: Optional[int] = Form(None),
    hours: Optional[float] = Form(None),
    include_saturday: bool = Form(True),
    include_sunday: bool = Form(False),
    confirm_conflicts: bool = Form(False),
    db: Session = Depends(deps.get_db),
    user: User = Depends(deps.get_current_user)
):
    if user.role not in [ADMIN, SUPERVISOR]:
        raise HTTPException(status_code=403, detail="Not authorized")
        
    start_date = datetime.strptime(date_val, "%Y-%m-%d").date()
    final_date = start_date
    if end_date:
        final_date = datetime.strptime(end_date, "%Y-%m-%d").date()
        if final_date < start_date:
             return JSONResponse({"status": "error", "message": "La fecha final no puede ser menor a la inicial"}, status_code=400)
    
    # Iterate from start to end
    from datetime import timedelta
    delta = final_date - start_date
    
    import json
    tasks_data = []
    try:
        tasks_data = json.loads(tasks_json)
    except json.JSONDecodeError:
        pass

    # A range skips the days not chosen (by default Sunday); a single day is always kept.
    days = [start_date + timedelta(days=i) for i in range(delta.days + 1)]
    if len(days) > 1:
        days = [d for d in days if (d.weekday() != 5 or include_saturday) and (d.weekday() != 6 or include_sunday)]
    if not days:
        return JSONResponse({"status": "error", "message": "El rango no tiene días para asignar"}, status_code=400)
    found = conflicts(db, user_id, days)
    if found and not confirm_conflicts:
        return conflict_response(found)
    location_id = check_location(db, project_id, location_id)
    planned = hours if hours and hours > 0 else 8.0

    # One creation time for the whole range: it is how its days are edited or removed together.
    created = datetime.utcnow()
    for current_day in days:
        new_schedule = ProjectSchedule(
            created_at=created,
            project_id=project_id,
            user_id=user_id,
            location_id=location_id,
            hours_worked=planned,
            date=current_day
        )
        db.add(new_schedule)
        db.flush()
        
        # Save tasks for this day
        for task in tasks_data:
            title = task.get("title", "")
            desc = task.get("description", "")
            if title.strip() or desc.strip():
                db.add(ScheduleTask(
                    schedule_id=new_schedule.id, 
                    title=title.strip(),
                    description=desc.strip()
                ))

    db.commit()
    log_activity(db, user, "CREATE", "SCHEDULE", None,
                 f"Asignó a {person_name(db, user_id)} en {project_name(db, project_id)}: {start_date:%d/%m/%Y}"
                 + (f" al {final_date:%d/%m/%Y} ({len(days)} días)" if final_date != start_date else ""))

    message = "Asignación creada correctamente" if len(days) == 1 else f"{len(days)} asignaciones creadas"
    return JSONResponse({"status": "success", "message": message})

@router.post("/schedule/{id}/delete")
def delete_schedule(id: int, scope: str = Form("one"), db: Session = Depends(deps.get_db),
                    user: User = Depends(deps.get_current_user)):
    if user.role not in [ADMIN, SUPERVISOR]:
        raise HTTPException(status_code=403, detail="Not authorized")
    
    schedule = db.query(ProjectSchedule).filter(ProjectSchedule.id == id).first()
    if not schedule:
        return JSONResponse({"status": "error", "message": "Asignación no encontrada"}, status_code=404)
        
    targets = schedules_in_scope(db, schedule, scope)
    days = ", ".join(f"{s.date:%d/%m}" for s in targets)
    details = (f"Quitó {'las asignaciones' if len(targets) > 1 else 'la asignación'} de "
               f"{person_name(db, schedule.user_id)} en {project_name(db, schedule.project_id)}: {days}")
    for target in targets:
        db.delete(target)
    db.commit()
    log_activity(db, user, "DELETE", "SCHEDULE", id, details)
    message = "Asignación eliminada correctamente" if len(targets) == 1 else f"{len(targets)} asignaciones eliminadas"
    return JSONResponse({"status": "success", "message": message})

@router.post("/schedule/{id}/edit")
def update_schedule(
    id: int,
    project_id: int = Form(...),
    user_id: int = Form(...),
    date_val: str = Form(..., alias="date"),
    tasks_json: str = Form("[]"),
    location_id: Optional[int] = Form(None),
    hours: Optional[float] = Form(None),
    confirm_conflicts: bool = Form(False),
    scope: str = Form("one"),
    db: Session = Depends(deps.get_db),
    user: User = Depends(deps.get_current_user)
):
    if user.role not in [ADMIN, SUPERVISOR]:
        raise HTTPException(status_code=403, detail="Not authorized")

    schedule = db.query(ProjectSchedule).filter(ProjectSchedule.id == id).first()
    if not schedule:
        return JSONResponse({"status": "error", "message": "Asignación no encontrada"}, status_code=404)

    import json
    try:
        tasks_data = json.loads(tasks_json)
    except json.JSONDecodeError:
        tasks_data = []
    if scope == "group":
        location_id = check_location(db, schedule.project_id, location_id)
        # Every day of the range: sede, planned hours and tasks (each day keeps its date,
        # project and person; its ticked tasks stay ticked).
        targets = schedules_in_scope(db, schedule, "group")
        for target in targets:
            target.location_id = location_id
            if hours and hours > 0 and not target.is_confirmed:
                target.hours_worked = hours
            apply_tasks(db, target, tasks_data, by_id=target.id == schedule.id)
        db.commit()
        log_activity(db, user, "UPDATE", "SCHEDULE", id,
                     f"Editó {len(targets)} asignaciones de {person_name(db, schedule.user_id)} en "
                     f"{project_name(db, schedule.project_id)} (sede, horas y tareas)")
        return JSONResponse({"status": "success", "message": f"{len(targets)} asignaciones actualizadas"})

    location_id = check_location(db, project_id, location_id)
    new_date = datetime.strptime(date_val, "%Y-%m-%d").date()
    found = conflicts(db, user_id, [new_date], exclude_id=id)
    if found and not confirm_conflicts:
        return conflict_response(found)

    schedule.project_id = project_id
    schedule.user_id = user_id
    schedule.date = new_date
    schedule.location_id = location_id
    # Planned hours only while they are not confirmed (after that, Aprobar Horas owns them).
    if hours and hours > 0 and not schedule.is_confirmed:
        schedule.hours_worked = hours
    apply_tasks(db, schedule, tasks_data)

    db.commit()
    log_activity(db, user, "UPDATE", "SCHEDULE", id,
                 f"Editó la asignación de {person_name(db, schedule.user_id)} en "
                 f"{project_name(db, schedule.project_id)} del {schedule.date:%d/%m/%Y}")
    return JSONResponse({"status": "success", "message": "Asignación actualizada correctamente"})

@router.post("/schedule/{id}/move")
def move_schedule(id: int, date_val: str = Form(..., alias="date"), confirm_conflicts: bool = Form(False),
                  db: Session = Depends(deps.get_db), user: User = Depends(deps.get_current_user)):
    """Drag and drop in the calendar: only the day changes."""
    if user.role not in [ADMIN, SUPERVISOR]:
        raise HTTPException(status_code=403, detail="Not authorized")
    schedule = db.query(ProjectSchedule).filter(ProjectSchedule.id == id).first()
    if not schedule:
        return JSONResponse({"status": "error", "message": "Asignación no encontrada"}, status_code=404)
    new_date = datetime.strptime(date_val, "%Y-%m-%d").date()
    if schedule.is_confirmed:
        return JSONResponse({"status": "error", "message": "Esa asignación ya tiene las horas confirmadas: no se mueve."},
                            status_code=400)
    found = conflicts(db, schedule.user_id, [new_date], exclude_id=id)
    if found and not confirm_conflicts:
        return conflict_response(found)
    old = schedule.date
    schedule.date = new_date
    db.commit()
    log_activity(db, user, "UPDATE", "SCHEDULE", id,
                 f"Movió la asignación de {person_name(db, schedule.user_id)} en {project_name(db, schedule.project_id)}"
                 f" del {old:%d/%m/%Y} al {new_date:%d/%m/%Y}")
    return JSONResponse({"status": "success", "message": "Asignación movida"})


@router.post("/task/{id}/toggle")
def toggle_task_status(id: int, db: Session = Depends(deps.get_db), user: User = Depends(deps.get_current_user)):
    task = db.query(ScheduleTask).filter(ScheduleTask.id == id).first()
    if not task:
        return JSONResponse({"status": "error", "message": "Tarea no encontrada"}, status_code=404)
    
    # Check authorization: Admin, Supervisor, or the assigned worker
    if user.role not in [ADMIN, SUPERVISOR] and task.schedule.user_id != user.id:
         raise HTTPException(status_code=403, detail="Not authorized")

    task.completed = not task.completed
    db.commit()
    
    return JSONResponse({
        "status": "success", 
        "message": "Estado actualizado", 
        "completed": task.completed
    })
