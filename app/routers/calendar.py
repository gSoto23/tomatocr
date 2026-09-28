
from typing import List, Optional
from datetime import datetime
from fastapi import APIRouter, Body, Depends, Form, Request, status, HTTPException
from fastapi.responses import RedirectResponse, JSONResponse
from sqlalchemy.orm import Session

from pydantic import BaseModel

from app.db.models.payroll import PayrollPeriod
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

# Fixed, readable colors: each project always gets the same one.
PROJECT_COLORS = ("#1d4ed8", "#047857", "#b45309", "#7c3aed", "#be123c", "#0e7490", "#4d7c0f", "#a21caf",
                  "#c2410c", "#334155")


def project_color(project_id: int) -> str:
    return PROJECT_COLORS[(project_id or 0) % len(PROJECT_COLORS)]


def member_payload(s: ProjectSchedule, group_sizes: dict) -> dict:
    return {
        "id": s.id,
        "worker_id": s.user_id,
        "worker_name": s.user.full_name or s.user.username,
        "project_id": s.project_id,
        "project_name": s.project.name,
        "location_id": s.location_id,
        "location_name": s.location.name if s.location else None,
        "hours": s.hours_worked,
        "overtime": s.overtime_hours or 0.0,
        "confirmed": bool(s.is_confirmed),
        "group_size": group_sizes.get(group_key(s), 1),
        "tasks": [{"id": t.id, "title": t.title, "description": t.description, "completed": t.completed}
                  for t in s.tasks],
    }


@router.get("/events")
def get_events(start: str, end: str, db: Session = Depends(deps.get_db), user: User = Depends(deps.get_current_user)):
    query = db.query(ProjectSchedule)
    is_manager = user.role in [ADMIN, SUPERVISOR]
    if not is_manager:
        query = query.filter(ProjectSchedule.user_id == user.id)
    schedules = [s for s in query.filter(ProjectSchedule.date >= start, ProjectSchedule.date <= end)
                 .order_by(ProjectSchedule.date).all() if s.user and s.project]

    if not is_manager:
        # A worker sees their own days, and taps one to open the project.
        return JSONResponse([{
            "id": s.id,
            "title": s.project.name + (f" · {s.location.name}" if s.location else ""),
            "start": s.date.isoformat(),
            "extendedProps": {**member_payload(s, {}), "url": f"/projects/{s.project.id}"},
            "color": project_color(s.project_id),
        } for s in schedules])

    # Admin and supervisor: one event per project and day, with its people inside.
    group_sizes = {key: group_query(db, *key).count() for key in {group_key(s) for s in schedules}}
    days = {}
    for s in schedules:
        days.setdefault((s.project_id, s.date), []).append(s)
    events = []
    for (project_id, day), members in days.items():
        members.sort(key=lambda m: (m.user.full_name or m.user.username).lower())
        all_confirmed = all(m.is_confirmed for m in members)
        count = len(members)
        events.append({
            "id": f"p{project_id}-{day.isoformat()}",
            "title": f"{'✓ ' if all_confirmed else ''}{members[0].project.name} · {count} "
                     f"{'persona' if count == 1 else 'personas'}",
            "start": day.isoformat(),
            "color": project_color(project_id),
            "borderColor": "#16a34a" if all_confirmed else project_color(project_id),
            "classNames": ["tomato-confirmed"] if all_confirmed else [],
            "extendedProps": {
                "project_id": project_id,
                "project_name": members[0].project.name,
                "date": day.isoformat(),
                "all_confirmed": all_confirmed,
                "members": [member_payload(m, group_sizes) for m in members],
            },
        })
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
    listed = ", ".join(f"{s.user.full_name or s.user.username if s.user else '?'} el {s.date:%d/%m} "
                       f"({s.project.name if s.project else '?'})" for s in found[:5])
    more = f" y {len(found) - 5} más" if len(found) > 5 else ""
    return JSONResponse({"status": "conflict", "message": f"Ya tiene asignación: {listed}{more}. "
                         "¿Asignar igual?"}, status_code=409)


def person_name(db: Session, user_id: int) -> str:
    person = db.get(User, user_id)
    return (person.full_name or person.username) if person else f"usuario {user_id}"


def project_name(db: Session, project_id: int) -> str:
    project = db.get(Project, project_id)
    return project.name if project else f"proyecto {project_id}"


@router.post("/schedule")
def create_schedule(
    project_id: int = Form(...),
    user_id: Optional[int] = Form(None),
    user_ids: List[int] = Form([]),
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
    # One or several people (the calendar assigns a project to its team).
    people = list(dict.fromkeys([*user_ids, *([user_id] if user_id else [])]))
    if not people:
        return JSONResponse({"status": "error", "message": "Elegí al menos una persona"}, status_code=400)
    found = [c for person in people for c in conflicts(db, person, days)]
    if found and not confirm_conflicts:
        return conflict_response(found)
    location_id = check_location(db, project_id, location_id)
    planned = hours if hours and hours > 0 else 8.0

    # One creation time for the whole range: it is how its days are edited or removed together.
    created = datetime.utcnow()
    for person, current_day in ((p, d) for p in people for d in days):
        new_schedule = ProjectSchedule(
            created_at=created,
            project_id=project_id,
            user_id=person,
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
    names = ", ".join(person_name(db, p) for p in people)
    log_activity(db, user, "CREATE", "SCHEDULE", None,
                 f"Asignó a {names} en {project_name(db, project_id)}: {start_date:%d/%m/%Y}"
                 + (f" al {final_date:%d/%m/%Y} ({len(days)} días)" if final_date != start_date else ""))

    total = len(days) * len(people)
    message = "Asignación creada correctamente" if total == 1 else f"{total} asignaciones creadas"
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


class HoursItem(BaseModel):
    id: int
    hours: float
    overtime: float = 0.0


def in_final_payroll(db: Session, day) -> bool:
    return db.query(PayrollPeriod.id).filter(PayrollPeriod.status == "final", PayrollPeriod.start_date <= day,
                                             PayrollPeriod.end_date >= day).first() is not None


@router.post("/day/confirm-hours")
def confirm_day_hours(items: List[HoursItem] = Body(...), db: Session = Depends(deps.get_db),
                      user: User = Depends(deps.get_current_user)):
    """From the project's day in the calendar: set and confirm each person's hours.
    A supervisor never confirms their own hours, and a day in a final payroll is closed."""
    if user.role not in [ADMIN, SUPERVISOR]:
        raise HTTPException(status_code=403, detail="Not authorized")
    done, skipped = 0, []
    for item in items:
        schedule = db.get(ProjectSchedule, item.id)
        if not schedule:
            continue
        name = schedule.user.full_name or schedule.user.username if schedule.user else "?"
        if user.role == SUPERVISOR and schedule.user_id == user.id:
            skipped.append(f"{name} (tus propias horas las confirma el admin)")
            continue
        if in_final_payroll(db, schedule.date):
            skipped.append(f"{name} (el día ya está en una planilla final)")
            continue
        if not (0 <= item.hours <= 24 and 0 <= item.overtime <= 24):
            skipped.append(f"{name} (horas fuera de rango)")
            continue
        schedule.hours_worked, schedule.overtime_hours, schedule.is_confirmed = item.hours, item.overtime, True
        done += 1
    db.commit()
    if done:
        log_activity(db, user, "Aprobar Horas", "SCHEDULE", items[0].id if items else None,
                     f"Confirmó las horas de {done} persona(s) desde el calendario")
    message = f"{done} hora(s) confirmadas" + (f". Sin cambiar: {'; '.join(skipped)}" if skipped else "")
    return JSONResponse({"status": "success" if done else "error", "message": message, "confirmed": done},
                        status_code=200 if done or not skipped else 400)


@router.post("/day/move")
def move_day(project_id: int = Form(...), from_date: str = Form(...), to_date: str = Form(...),
             confirm_conflicts: bool = Form(False), db: Session = Depends(deps.get_db),
             user: User = Depends(deps.get_current_user)):
    """Drag a project's day to another day: everyone moves, except days with confirmed hours."""
    if user.role not in [ADMIN, SUPERVISOR]:
        raise HTTPException(status_code=403, detail="Not authorized")
    source = datetime.strptime(from_date, "%Y-%m-%d").date()
    target = datetime.strptime(to_date, "%Y-%m-%d").date()
    members = db.query(ProjectSchedule).filter(ProjectSchedule.project_id == project_id,
                                               ProjectSchedule.date == source).all()
    if any(m.is_confirmed for m in members):
        return JSONResponse({"status": "error", "message": "Ese día ya tiene horas confirmadas: no se mueve."},
                            status_code=400)
    found = [c for m in members for c in conflicts(db, m.user_id, [target], exclude_id=m.id)]
    if found and not confirm_conflicts:
        return conflict_response(found)
    for m in members:
        m.date = target
    db.commit()
    log_activity(db, user, "UPDATE", "SCHEDULE", None,
                 f"Movió {project_name(db, project_id)} del {source:%d/%m/%Y} al {target:%d/%m/%Y} ({len(members)} personas)")
    return JSONResponse({"status": "success", "message": f"Día movido ({len(members)} personas)"})


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
