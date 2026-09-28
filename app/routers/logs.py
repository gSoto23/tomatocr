
import uuid
import json
from pathlib import Path
from datetime import datetime, date, timedelta
from typing import List, Optional

from fastapi import APIRouter, Depends, Form, File, UploadFile, status, Request, HTTPException
from fastapi.responses import RedirectResponse, JSONResponse
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.db.models.log import DailyLog, Photo
from app.db.models.project import Project
from app.db.models.log_task import DailyLogTask
from app.db.models.user import User
from app.db.models.associations import project_users
from app.routers import deps
from app.db.models.reforestation import ReforestationProject
from app.utils.crm import report_recipients
from app.core.roles import ADMIN, CLIENT, OPERATIONS_ROLES
from app.utils.activity import log_activity
from app.core.config import settings
from app.utils.timecr import today_cr
from app.utils.uploads import PHOTO_RULES, process_photo

MAX_DAYS_BACK = 7  # a report can be for a forgotten day, up to a week back

router = APIRouter(
    prefix="/logs",
    tags=["logs"],
    dependencies=[Depends(deps.require_roles(*OPERATIONS_ROLES))]
)

from app.core.templates import templates

@router.get("/")
def list_logs(
    request: Request, 
    project_id: Optional[int] = None,
    page: int = 1,
    limit: int = 10,
    sort: str = "date",
    order: str = "desc",
    db: Session = Depends(deps.get_db), 
    user: User = Depends(deps.get_current_user)
):
    # RBAC: Admin sees all, others see only assigned projects
    if user.role == ADMIN:
        count_query = db.query(func.count(DailyLog.id)).join(Project)
        query = db.query(DailyLog).join(Project)
    else:
        # Filter for Client/Worker
        count_query = db.query(func.count(DailyLog.id))\
            .join(Project)\
            .join(project_users, Project.id == project_users.c.project_id)\
            .filter(project_users.c.user_id == user.id)
            
        query = db.query(DailyLog)\
            .join(Project)\
            .join(project_users, Project.id == project_users.c.project_id)\
            .filter(project_users.c.user_id == user.id)

    # Filter by Project if provided (and authorized)
    if project_id:
        # Check authorization for specific project if not admin
        if user.role != ADMIN:
            # Verify user belongs to this project
            is_member = db.query(project_users).filter(
                project_users.c.user_id == user.id,
                project_users.c.project_id == project_id
            ).first()
            if not is_member:
                raise HTTPException(status_code=403, detail="Not authorized for this project")
                
        query = query.filter(DailyLog.project_id == project_id)
        count_query = count_query.filter(DailyLog.project_id == project_id)

    total_records = count_query.scalar()

    # Sorting
    if sort == "project":
        if order == "asc":
            query = query.order_by(Project.name.asc())
        else:
            query = query.order_by(Project.name.desc())
    else: # Default date
        if order == "asc":
            query = query.order_by(DailyLog.date.asc(), DailyLog.created_at.asc())
        else:
            query = query.order_by(DailyLog.date.desc(), DailyLog.created_at.desc())

    # Pagination
    offset = (page - 1) * limit
    logs = query.offset(offset).limit(limit).all()
    
    # Get all projects for filter dropdown
    projects = db.query(Project).all()
    
    from math import ceil
    total_pages = ceil(total_records / limit)
    
    return templates.TemplateResponse("logs/list.html", {
        "request": request, 
        "logs": logs, 
        "user": user,
        "projects": projects,
        "selected_project_id": project_id,
        "page": page,
        "total_pages": total_pages,
        "total_records": total_records,
        "sort": sort,
        "order": order
    })

@router.get("/{id}/detail")
def get_log_detail(id: int, db: Session = Depends(deps.get_db), user: User = Depends(deps.get_current_user)):
    log = db.query(DailyLog).filter(DailyLog.id == id).first()
    if not log:
        raise HTTPException(status_code=404, detail="Log not found")
    
    # Auth check: Admin, Author, or Assigned User (Client/Worker)
    is_project_member = False
    if log.project and log.project.users:
        is_project_member = user.id in [u.id for u in log.project.users]

    if user.role != ADMIN and log.user_id != user.id and not is_project_member:
        raise HTTPException(status_code=403, detail="Not authorized")

    # The project's current tasks (to allow checking missed ones) plus any archived
    # task this report had completed, so old reports keep showing it.
    completed_task_ids = {entry.task_id for entry in log.task_entries}
    all_project_tasks = list(log.project.tasks) + [
        entry.task for entry in log.task_entries
        if entry.task is not None and entry.task.archived_at is not None]

    tasks_data = []
    for task in all_project_tasks:
        tasks_data.append({
            "task_id": task.id,
            "description": task.description,
            "completed": task.id in completed_task_ids,
            "is_required": task.is_required
        })
    
    # Get Project Contacts for Email Dropdown
    # Recipients: the account contacts marked "recibe reportes" for this project (Clientes).
    contacts_data = report_recipients(db, log.project) if log.project else []

    return {
        "id": log.id,
        "project_name": log.project.name,
        "location_name": log.location.name if log.location else None,
        "user_name": log.user.full_name or log.user.username,
        "date": log.date.strftime('%Y-%m-%d'),
        "notes": log.notes,
        "photos": [{"file_path": p.file_path} for p in log.photos],
        "created_at": log.created_at.isoformat() if log.created_at else None,
        "updated_at": log.updated_at.isoformat() if log.updated_at else None,
        "can_edit": (user.role == ADMIN or log.user_id == user.id),
        "is_admin": (user.role == ADMIN),
        "tasks": tasks_data,
        "project_contacts": contacts_data
    }

@router.post("/{id}/delete")
def delete_log(id: int, db: Session = Depends(deps.get_db), user: User = Depends(deps.get_current_user)):
    log = db.query(DailyLog).filter(DailyLog.id == id).first()
    if not log:
        raise HTTPException(status_code=404, detail="Log not found")

    if user.role != ADMIN and log.user_id != user.id:
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
    
    # Audit Log
    try:
        log_activity(db, user=user, action="DELETE", entity_type="REPORT", entity_id=id, details=f"Eliminó reporte de proyecto ID {project_id}")
    except Exception as e:
        print(f"Audit Log Error: {e}")
        
    response = RedirectResponse(url=f"/projects/{project_id}", status_code=status.HTTP_303_SEE_OTHER)
    response.set_cookie(key="toast_message", value="Reporte eliminado correctamente")
    return response

@router.post("/{id}/edit")
def update_log(
    id: int,
    notes: str = Form(...),
    location_id: Optional[int] = Form(None),
    task_ids: List[int] = Form([], alias="tasks"),
    db: Session = Depends(deps.get_db),
    user: User = Depends(deps.get_current_user)
):
    log = db.query(DailyLog).filter(DailyLog.id == id).first()
    if not log:
        raise HTTPException(status_code=404, detail="Log not found")

    if user.role != ADMIN and log.user_id != user.id:
        raise HTTPException(status_code=403, detail="Not authorized")
    
    log.notes = notes
    # The edit window doesn't show the sede: keep it unless one is sent.
    if location_id:
        log.location_id = location_id
    
    # Update tasks
    # Clear existing tasks? Or merge?
    # Usually easier to clear and re-add for checklist behavior
    db.query(DailyLogTask).filter(DailyLogTask.log_id == id).delete()
    
    for t_id in task_ids:
        db.add(DailyLogTask(log_id=log.id, task_id=t_id, completed=True))

    db.commit()
    db.commit()
    
    # Audit Log
    try:
        log_activity(db, user=user, action="UPDATE", entity_type="REPORT", entity_id=log.id, details=f"Editó reporte del proyecto ID {log.project_id}")
    except Exception as e:
        print(f"Audit Log Error: {e}")
        
    response = RedirectResponse(url=f"/projects/{log.project_id}", status_code=status.HTTP_303_SEE_OTHER)
    response.set_cookie(key="toast_message", value="Reporte actualizado correctamente")
    return response

@router.get("/new")
def new_log_form(request: Request, project_id: Optional[int] = None, db: Session = Depends(deps.get_db), user: User = Depends(deps.get_current_user)):
    # RBAC: Clients cannot report
    if user.role == CLIENT:
        return RedirectResponse(url="/projects", status_code=status.HTTP_303_SEE_OTHER)

    # Get available projects
    if user.role == ADMIN:
        projects = db.query(Project).filter(Project.is_active == True).all()
    else:
        # Worker: only assigned active projects
        # Explicit query to avoid DetachedInstanceError with lazy loading
        projects = db.query(Project)\
            .join(project_users)\
            .filter(project_users.c.user_id == user.id)\
            .filter(Project.is_active == True)\
            .all()

    # Pre-fetch tasks and locations for all available projects to pass to JS
    project_tasks_map = {}
    project_locations_map = {}
    for p in projects:
        project_tasks_map[p.id] = [
            {"id": t.id, "description": t.description, "is_required": t.is_required} 
            for t in p.tasks
        ]
        project_locations_map[p.id] = [
            {"id": loc.id, "name": loc.name}
            for loc in p.locations
        ]

    today = today_cr()
    project_tasks_json = json.dumps(project_tasks_map)
    project_locations_json = json.dumps(project_locations_map)
    
    return templates.TemplateResponse("logs/form.html", {
        "request": request,
        "user": user, 
        "projects": projects,
        "today": today,
        "earliest": today - timedelta(days=MAX_DAYS_BACK),
        "photo_rules": PHOTO_RULES,
        "project_tasks_json": project_tasks_json,
        "project_locations_json": project_locations_json,
        "selected_project_id": project_id,
        "monitored_project_ids": [
            pid for (pid,) in db.query(ReforestationProject.project_id).filter(
                ReforestationProject.project_id.in_([p.id for p in projects])
            )
        ],
    })

@router.post("/new")
def create_log(
    project_id: int = Form(...),
    location_id: Optional[int] = Form(None),
    date_val: str = Form(..., alias="date"),
    notes: str = Form(""),
    task_ids: List[int] = Form([], alias="tasks"), # IDs of completed tasks
    photos: List[UploadFile] = File(default=None),
    db: Session = Depends(deps.get_db),
    user: User = Depends(deps.get_current_user)
):
    if user.role == CLIENT:
         return RedirectResponse(url="/projects", status_code=status.HTTP_303_SEE_OTHER)
    
    # Validation
    if user.role != ADMIN:
        assigned = db.query(Project).filter(Project.id == project_id, Project.users.any(id=user.id)).first()
        if not assigned:
             response = RedirectResponse(url="/projects", status_code=status.HTTP_303_SEE_OTHER)
             response.set_cookie(key="toast_message", value="No tienes permiso para reportar en este proyecto")
             response.set_cookie(key="toast_type", value="error")
             return response

    # The day can be up to MAX_DAYS_BACK in the past (a forgotten day), never in the future.
    try:
        log_date = datetime.strptime(date_val, "%Y-%m-%d").date()
    except ValueError:
        raise HTTPException(status_code=400, detail="La fecha del reporte no es válida")
    today = today_cr()
    if not (today - timedelta(days=MAX_DAYS_BACK) <= log_date <= today):
        raise HTTPException(status_code=400, detail=f"La fecha tiene que ser de hoy o de los últimos {MAX_DAYS_BACK} días")

    # Every photo is checked and processed before anything is saved, so one bad photo
    # doesn't lose the report: the page shows which file failed and keeps what was typed.
    processed = []
    for photo in photos or []:
        if photo.filename:
            processed.append(process_photo(photo.file.read(), photo.content_type, photo.filename))

    # Create Log
    new_log = DailyLog(
        project_id=project_id,
        location_id=location_id if location_id else None,
        user=user,
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

    # Save the processed photos (JPEG).
    if processed:
        year_month = log_date.strftime("%Y/%m")
        target_dir = Path("app/static/uploads") / year_month
        target_dir.mkdir(parents=True, exist_ok=True)
        for contents in processed:
            unique_name = f"{uuid.uuid4()}.jpg"
            with open(target_dir / unique_name, "wb") as buffer:
                buffer.write(contents)
            db.add(Photo(log_id=new_log.id, file_path=f"/static/uploads/{year_month}/{unique_name}"))

    db.commit()
    
    # Audit Log
    try:
        log_activity(db, user=user, action="CREATE", entity_type="REPORT", entity_id=new_log.id, details=f"Reporte de avance para {log_date}")
    except Exception as e:
        print(f"Audit Log Error: {e}")
        
    response = RedirectResponse(url=f"/projects/{project_id}", status_code=status.HTTP_303_SEE_OTHER)
    response.set_cookie(key="toast_message", value="Reporte creado correctamente")
    return response

from app.utils.email import send_log_email
from pydantic import EmailStr, BaseModel

class EmailSchema(BaseModel):
    recipients: List[EmailStr]
    additional_text: Optional[str] = None
    custom_notes: Optional[str] = None

from fastapi import BackgroundTasks

@router.post("/{id}/send-email")
async def send_email(
    id: int,
    email_data: EmailSchema,
    db: Session = Depends(deps.get_db),
    user: User = Depends(deps.get_current_user)
):
    if user.role != ADMIN:
        raise HTTPException(status_code=403, detail="Not authorized")

    log = db.query(DailyLog).filter(DailyLog.id == id).first()
    if not log:
        raise HTTPException(status_code=404, detail="Log not found")

    # Sent now (not in the background) so the screen tells the truth; the company copy
    # goes as a real blind copy, added here and never shown to the client.
    bcc = settings.REPORT_BCC_EMAIL
    recipients = [r for r in email_data.recipients if r.lower() != (bcc or "").lower()]
    if not recipients:
        raise HTTPException(status_code=400, detail="Elegí al menos un destinatario")
    sent = await send_log_email(log.id, recipients, email_data.additional_text, email_data.custom_notes,
                                bcc=[bcc] if bcc else [])
    if not sent:
        raise HTTPException(status_code=502, detail="No se pudo enviar el correo. Revisá las direcciones y probá de "
                                                    "nuevo; si sigue fallando, avisale al admin del sistema.")

    # Audit Log
    try:
        details = {
            "mensaje": f"Reporte #{log.id} enviado por correo.",
            "destinatarios": recipients,
            "notas_adicionales": email_data.additional_text or "Ninguna"
        }
        log_activity(db, user=user, action="EMAIL", entity_type="REPORT", entity_id=log.id, details=details)
    except Exception as e:
        print(f"Audit Log Error: {e}")
    
    return JSONResponse({"status": "success", "message": "Correo enviado"})
