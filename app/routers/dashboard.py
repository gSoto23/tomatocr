from fastapi import APIRouter, Depends, Request
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from sqlalchemy import desc

from app.db.session import SessionLocal
from app.routers import deps
from app.db.models.user import User
from app.db.models.project import Project
from app.db.models.finance import Invoice, InvoiceStatus
from app.db.models.log import DailyLog
from app.db.models.schedule import ProjectSchedule
from app.db.models.associations import project_users
from app.routers.finance import get_project_budget_status

router = APIRouter(
    prefix="/dashboard",
    tags=["dashboard"],
    dependencies=[Depends(deps.get_current_user)]
)

from app.core.templates import templates

@router.get("/")
async def dashboard(
    request: Request, 
    start_date: str = None, 
    end_date: str = None, 
    invoice_status: str = None,
    db: Session = Depends(deps.get_db), 
    user: User = Depends(deps.get_current_user)
):
    data = {}
    
    if user.role == "admin":
        # 1. Stats
        active_projects = db.query(Project).filter(Project.is_active == True).all()
        active_count = len(active_projects)
        
        total_adjudicated = 0.0
        # Calculate Total Adjudicated (Unfiltered typically)
        for p in active_projects:
            # Reusing finance logic for adjudication only
            stats = get_project_budget_status(db, p)
            total_adjudicated += stats["total_adjudicated"]
        
        # Calculate Total Invoiced (Filtered)
        # Query all invoices for active projects
        active_project_ids = [p.id for p in active_projects]
        invoices_query = db.query(Invoice).join(ProjectSchedule, Invoice.budget_id == ProjectSchedule.id, isouter=True) 
        # Wait, Invoice links to ProjectBudget via budget_id? 
        # Let's check models. Project -> ProjectBudget -> Invoice?
        # Invoice.budget_id -> ProjectBudget.id. ProjectBudget.project_id -> Project.id
        
        # Simpler: query Invoice joined with ProjectBudget joined with Project
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
        
    elif user.role == "client":
        # 1. Get Client Projects for Dropdown & Filter
        client_projects = db.query(Project).join(project_users).filter(project_users.c.user_id == user.id).all()
        project_ids = [p.id for p in client_projects]
        
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
        data["projects"] = client_projects
        data["selected_project_id"] = selected_project_id
        data["page"] = page
        data["total_pages"] = total_pages
        data["total_records"] = total_records
        data["sort"] = sort
        data["order"] = order
        
    elif user.role == "worker":
        # 1. Recent Activity: Assignments (Schedule)
        # Order by date desc (future first? or past? typically recent means latest)
        # User said "lista de Asignación definidas en el calendario"
        assignments = db.query(ProjectSchedule).filter(
            ProjectSchedule.user_id == user.id
        ).order_by(ProjectSchedule.date.desc()).limit(20).all()
        
        data["recent_activity"] = assignments

    return templates.TemplateResponse("dashboard.html", {
        "request": request, 
        "user": user, 
        "data": data
    })
