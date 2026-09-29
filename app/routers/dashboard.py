from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Form, HTTPException, Request, status
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
from sqlalchemy import desc

from app.routers import deps
from app.core.roles import ADMIN, CLIENT, SUPERVISOR, VENTAS, WORKER
from app.utils import crm
from app.utils.timecr import today_cr
from app.db.models.user import User
from app.db.models.project import Project
from app.db.models.finance import Invoice, InvoiceStatus
from app.db.models.log import DailyLog
from app.db.models.schedule import ProjectSchedule
from app.db.models.associations import project_users
from app.db.models.task import PRIORITIES, PRIORITY_LABELS, Task
from app.utils.activity import log_activity
from app.utils.admin_overview import (LEVEL_LABELS, admin_overview, client_projects, sales_alerts, supervisor_overview,
                                      worker_alerts)
from app.utils.tasks import (assignable_users, can_manage, mark_seen, my_tasks, parse_task_form, split_alerts, unmark,
                             uses_tasks)
from app.routers.crm import toast_redirect
from app.routers.finance import check_update_overdue_invoices, get_project_budget_status

router = APIRouter(
    prefix="/dashboard",
    tags=["dashboard"],
    dependencies=[Depends(deps.get_current_user)]
)

from app.core.templates import templates

@router.get("/")
def dashboard(
    request: Request, 
    start_date: str = None, 
    end_date: str = None, 
    invoice_status: str = None,
    db: Session = Depends(deps.get_db), 
    user: User = Depends(deps.get_current_user)
):
    data = {}
    
    if user.role == ADMIN:
        # Overdue is otherwise only refreshed when a budget is opened.
        check_update_overdue_invoices(db)
        # 1. Stats
        active_projects = db.query(Project).filter(Project.is_active == True).all()
        active_count = len(active_projects)
        
        total_adjudicated = 0.0
        # Calculate Total Adjudicated (Unfiltered typically)
        for p in active_projects:
            # Reusing finance logic for adjudication only
            stats = get_project_budget_status(db, p)
            total_adjudicated += stats["total_adjudicated"]
        
        # Calculate Total Invoiced (Filtered): query Invoice joined with ProjectBudget joined with Project
        from app.db.models.finance import ProjectBudget
        
        base_query = db.query(Invoice).join(ProjectBudget).join(Project).filter(Project.is_active == True)
        
        # Apply Filters
        if start_date:
            base_query = base_query.filter(Invoice.issue_date >= start_date)
        if end_date:
            base_query = base_query.filter(Invoice.issue_date <= end_date)
        if invoice_status and invoice_status != "all":
            base_query = base_query.filter(Invoice.status == invoice_status)
            
        filtered_invoices = base_query.all()
        total_invoiced = sum(inv.amount for inv in filtered_invoices)

        data["stats"] = {
            "active_projects": active_count,
            "total_adjudicated": total_adjudicated,
            "total_invoiced": total_invoiced
        }
        
        # 2. Recent Activity: Invoices
        # If no filters, show default Pending/Partial/Overdue.
        # If filters exist, show filtered list.
        activity_query = base_query
        
        if not invoice_status and not start_date and not end_date:
             # Default behavior: Pending/Partial/Overdue
             pending_statuses = [InvoiceStatus.PENDING, InvoiceStatus.PARTIAL, InvoiceStatus.OVERDUE]
             activity_query = activity_query.filter(Invoice.status.in_(pending_statuses))
        
        # Order by due date
        recent_invoices = activity_query.order_by(Invoice.due_date.asc()).all()
        
        data["recent_activity"] = recent_invoices
        data["filtered"] = bool(start_date or end_date or invoice_status)
        data["crm_period"] = crm.funnel_period(db)
        data["crm_funnel"] = crm.funnel(db, period=data["crm_period"])
        data["crm_money"] = crm.money_progress(db, data["crm_period"])
        today = today_cr()
        period = data["crm_period"]
        data["crm_running"] = period.start <= today <= period.end
        data["overview"] = admin_overview(db, today, crm.next_steps(db, today=today), crm.expiring_contracts(db, today))
        data["alerts"] = data["overview"].alerts

    elif user.role == CLIENT:
        # 1. Get Client Projects for Dropdown & Filter
        client_projects_list = db.query(Project).join(project_users).filter(project_users.c.user_id == user.id).all()
        project_ids = [p.id for p in client_projects_list]
        
        # 2. Logs Query
        # If project_id param is provided, verify it belongs to client
        query = db.query(DailyLog).filter(DailyLog.project_id.in_(project_ids))
        
        selected_project_id = None
        if request.query_params.get("project_id"):
            try:
                pid = int(request.query_params.get("project_id"))
                if pid in project_ids:
                    query = query.filter(DailyLog.project_id == pid)
                    selected_project_id = pid
            except ValueError:
                pass
        
        # Sorting
        sort = request.query_params.get("sort", "date")
        order = request.query_params.get("order", "desc")
        
        if sort == "project":
            if order == "asc":
                query = query.join(Project).order_by(Project.name.asc())
            else:
                query = query.join(Project).order_by(Project.name.desc())
        else: # Default date
            if order == "asc":
                query = query.order_by(DailyLog.date.asc(), DailyLog.created_at.asc())
            else:
                query = query.order_by(DailyLog.date.desc(), DailyLog.created_at.desc())
        
        # Pagination
        page = int(request.query_params.get("page", 1))
        limit = 10
        total_records = query.count()
        
        from math import ceil
        total_pages = ceil(total_records / limit)
        offset = (page - 1) * limit
        
        logs = query.offset(offset).limit(limit).all()
        
        data["logs"] = logs
        data["today"] = today_cr()
        data["project_cards"] = client_projects(db, data["today"], client_projects_list)
        data["projects"] = client_projects_list
        data["selected_project_id"] = selected_project_id
        data["page"] = page
        data["total_pages"] = total_pages
        data["total_records"] = total_records
        data["sort"] = sort
        data["order"] = order
        
    elif user.role in [WORKER, SUPERVISOR]:
        # 1. Recent Activity: Assignments (Schedule)
        # Order by date desc (future first? or past? typically recent means latest)
        # User said "lista de Asignación definidas en el calendario"
        # Today and the next days first (nearest first), then the latest past ones.
        today = today_cr()
        data["upcoming"] = db.query(ProjectSchedule).filter(
            ProjectSchedule.user_id == user.id, ProjectSchedule.date >= today
        ).order_by(ProjectSchedule.date, ProjectSchedule.id).limit(15).all()
        data["past"] = db.query(ProjectSchedule).filter(
            ProjectSchedule.user_id == user.id, ProjectSchedule.date < today
        ).order_by(ProjectSchedule.date.desc()).limit(5).all()
        data["today"] = today
        data["today_assignments"] = [s for s in data["upcoming"] if s.date == today]
        if user.role == SUPERVISOR:
            # The team alert already covers the supervisor's own days without report.
            data["overview"] = supervisor_overview(db, today, user)
            data["alerts"] = data["overview"].alerts
        else:
            data["alerts"] = worker_alerts(db, today, user)

    elif user.role == VENTAS:
        today = today_cr()
        data["next_steps"] = crm.next_steps(db, owner_id=user.id, today=today)
        data["crm_period"] = crm.funnel_period(db)
        data["crm_running"] = data["crm_period"].start <= today <= data["crm_period"].end
        data["crm_funnel"] = crm.funnel(db, owner_id=user.id, period=data["crm_period"])
        data["alerts"] = sales_alerts(data["next_steps"])

    data["alerts"], data["pending_alerts"] = split_alerts(db, user, data.get("alerts", []))
    if uses_tasks(user):
        data["today"] = data.get("today") or today_cr()
        data["tasks"] = my_tasks(db, user, data["today"])
        data["assignable"] = assignable_users(db, user)
    return templates.TemplateResponse("dashboard.html", {
        "request": request, 
        "user": user, 
        "data": data,
        "priorities": PRIORITIES, "priority_labels": PRIORITY_LABELS, "level_labels": LEVEL_LABELS,
    })


def current_alerts(db: Session, user: User):
    """The alerts of this person's Dashboard, computed the same way as the page."""
    today = today_cr()
    if user.role == ADMIN:
        check_update_overdue_invoices(db)
        return admin_overview(db, today, crm.next_steps(db, today=today), crm.expiring_contracts(db, today)).alerts
    if user.role == SUPERVISOR:
        return supervisor_overview(db, today, user).alerts
    if user.role == WORKER:
        return worker_alerts(db, today, user)
    if user.role == VENTAS:
        return sales_alerts(crm.next_steps(db, owner_id=user.id, today=today))
    return []


@router.post("/alertas/{key}/visto")
def alert_seen(key: str, db: Session = Depends(deps.get_db), user: User = Depends(deps.get_current_user)):
    """'Ya lo vi': the alert moves to Pendientes for this person, even if it isn't fixed yet."""
    alert = next((a for a in current_alerts(db, user) if a.key == key), None)
    if alert is None:
        return toast_redirect("/dashboard/", "Esa alerta ya no está: se resolvió")
    mark_seen(db, user, alert)
    db.commit()
    return toast_redirect("/dashboard/", "Movida a Pendientes; vuelve a Nuevas si empeora")


@router.post("/alertas/{key}/volver")
def alert_back(key: str, db: Session = Depends(deps.get_db), user: User = Depends(deps.get_current_user)):
    unmark(db, user, key)
    db.commit()
    return toast_redirect("/dashboard/", "La alerta volvió a Requiere atención")


# --- Tareas ------------------------------------------------------------------------

def task_user(user: User = Depends(deps.get_current_user)) -> User:
    if not uses_tasks(user):
        raise HTTPException(status_code=403, detail="Las tareas son para el equipo")
    return user


def managed_task(db: Session, task_id: int, user: User) -> Task:
    task = db.get(Task, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Tarea no encontrada")
    if not can_manage(user, task):
        raise HTTPException(status_code=403, detail="Esa tarea es de otra persona")
    return task


@router.post("/tareas")
def create_task(title: str = Form(""), due_date: str = Form(""), priority: Optional[str] = Form(None),
                description: Optional[str] = Form(None), assignee_id: Optional[str] = Form(None),
                db: Session = Depends(deps.get_db), user: User = Depends(task_user)):
    try:
        fields = parse_task_form(db, user, title, due_date, priority, description, assignee_id)
    except ValueError as e:
        return toast_redirect("/dashboard/", str(e), error=True)
    task = Task(created_by_id=user.id, **fields)
    db.add(task)
    db.commit()
    if task.assignee_id != user.id:
        log_activity(db, user, "CREATE", "TASK", task.id, f"Tarea para {task.assignee.full_name or task.assignee.username}: {task.title}")
        return toast_redirect("/dashboard/", f"Tarea asignada a {task.assignee.full_name or task.assignee.username}")
    return toast_redirect("/dashboard/", "Tarea agregada")


@router.post("/tareas/{task_id}/hecha")
def toggle_task(task_id: int, db: Session = Depends(deps.get_db), user: User = Depends(task_user)):
    task = managed_task(db, task_id, user)
    task.done_at = None if task.done_at else datetime.utcnow()
    db.commit()
    return toast_redirect("/dashboard/", "Tarea hecha" if task.done_at else "Tarea pendiente otra vez")


@router.post("/tareas/{task_id}/editar")
def edit_task(task_id: int, title: str = Form(""), due_date: str = Form(""), priority: Optional[str] = Form(None),
              description: Optional[str] = Form(None), assignee_id: Optional[str] = Form(None),
              db: Session = Depends(deps.get_db), user: User = Depends(task_user)):
    task = managed_task(db, task_id, user)
    try:
        fields = parse_task_form(db, user, title, due_date, priority, description,
                                 assignee_id if assignee_id is not None else str(task.assignee_id))
    except ValueError as e:
        return toast_redirect("/dashboard/", str(e), error=True)
    for name, value in fields.items():
        setattr(task, name, value)
    db.commit()
    return toast_redirect("/dashboard/", "Tarea guardada")


@router.post("/tareas/{task_id}/borrar")
def delete_task(task_id: int, db: Session = Depends(deps.get_db), user: User = Depends(task_user)):
    task = managed_task(db, task_id, user)
    db.delete(task)
    db.commit()
    return toast_redirect("/dashboard/", "Tarea borrada")

@router.get("/activity")
def activity_log(
    request: Request,
    page: int = 1,
    limit: int = 50,
    q: str = "",
    db: Session = Depends(deps.get_db), 
    user: User = Depends(deps.get_current_user)
):
    if user.role != ADMIN:
        return RedirectResponse(url="/dashboard", status_code=status.HTTP_303_SEE_OTHER)

    from math import ceil
    from app.db.models.activity import ActivityLog
    from sqlalchemy.orm import joinedload

    from sqlalchemy import or_
    offset = (page - 1) * limit
    query = db.query(ActivityLog)
    q = q.strip()
    if q:
        # The search looks through the whole history, not only the page on screen.
        like = f"%{q}%"
        query = query.outerjoin(User, ActivityLog.user_id == User.id).filter(or_(
            User.username.ilike(like), User.full_name.ilike(like), ActivityLog.action.ilike(like),
            ActivityLog.entity_type.ilike(like), ActivityLog.details.ilike(like)))
    total_records = query.count()

    logs = query.options(joinedload(ActivityLog.user)).order_by(desc(ActivityLog.created_at)).offset(offset).limit(limit).all()
    
    total_pages = ceil(total_records / limit)

    return templates.TemplateResponse("admin/activity.html", {
        "request": request,
        "user": user,
        "logs": logs,
        "page": page,
        "total_pages": total_pages,
        "total_records": total_records,
        "q": q,
    })
