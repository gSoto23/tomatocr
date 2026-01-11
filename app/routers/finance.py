from typing import List, Optional
from fastapi import APIRouter, Depends, Request, HTTPException, status, Form
from fastapi.responses import RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from sqlalchemy import func
import datetime

from app.db.session import SessionLocal
from app.db.models.project import Project
from app.db.models.finance import ProjectBudget, BudgetLine, Invoice, Payment, InvoiceStatus
from app.db.models.user import User
from app.db.models.associations import project_users
from app.routers import deps

router = APIRouter(
    prefix="/finance",
    tags=["finance"],
    dependencies=[Depends(deps.get_current_user)]
)

templates = Jinja2Templates(directory="app/templates")

def check_finance_access(user: User):
    if user.role == "worker":
        raise HTTPException(status_code=403, detail="Forbidden")

def get_project_budget_status(db: Session, project: Project):
    # Calculate totals
    budget = db.query(ProjectBudget).filter(ProjectBudget.project_id == project.id).first()
    
    total_adjudicated = 0.0
    total_invoiced = 0.0
    
    if budget:
        # Sum lines (calculated properties not available in query easily, so loop or hybrid)
        # Using python loop for simplicity as N is small
        for line in budget.lines:
             # Tax calculation: subtotal + subtotal * (tax/100)
             total_adjudicated += line.subtotal * (1 + (line.tax_percentage / 100.0))
        
        # Add Prorogue
        if budget.is_prorrogable and budget.active_prorogue:
            total_adjudicated += budget.prorrogable_amount or 0.0
            
        # Sum Invoices
        for inv in budget.invoices:
            total_invoiced += inv.amount

    return {
        "budget": budget,
        "total_adjudicated": total_adjudicated,
        "total_invoiced": total_invoiced,
        "balance": total_adjudicated - total_invoiced
    }

def check_update_overdue_invoices(db: Session, project_id: int):
    today = datetime.date.today()
    # Find pending invoices past due
    overdue = db.query(Invoice).join(ProjectBudget).filter(
        ProjectBudget.project_id == project_id,
        Invoice.status == InvoiceStatus.PENDING,
        Invoice.due_date < today
    ).all()
    
    if overdue:
        for inv in overdue:
            inv.status = InvoiceStatus.OVERDUE
        db.commit()

@router.get("/")
async def finance_dashboard(request: Request, db: Session = Depends(deps.get_db), user: User = Depends(deps.get_current_user)):
    check_finance_access(user)
    
    # Get Projects
    if user.role == "admin":
        projects = db.query(Project).all()
    else:
        # Client
        projects = db.query(Project).join(project_users).filter(project_users.c.user_id == user.id).all()
    
    # Compile Data
    finance_projects = []
    for p in projects:
        status = get_project_budget_status(db, p)
        finance_projects.append({
            "project": p,
            "licitation": status["budget"].licitation_number if status["budget"] else "N/A",
            "total_adjudicated": status["total_adjudicated"],
            "total_invoiced": status["total_invoiced"],
            "balance": status["balance"]
        })

    return templates.TemplateResponse("finance/index.html", {
        "request": request, 
        "user": user, 
        "projects": finance_projects
    })

@router.get("/{project_id}")
async def finance_detail(
    project_id: int, 
    request: Request, 
    page: int = 1,
    limit: int = 10,
    status: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    sort_by: str = "issue_date",
    order: str = "desc",
    db: Session = Depends(deps.get_db), 
    user: User = Depends(deps.get_current_user)
):
    check_finance_access(user)
    
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
         raise HTTPException(status_code=404, detail="Project not found")

    if user.role == "client" and user.id not in [u.id for u in project.users]:
        raise HTTPException(status_code=403, detail="Not authorized")

    # Update Overdue Statuses
    check_update_overdue_invoices(db, project.id)

    status_data = get_project_budget_status(db, project)
    budget = status_data["budget"]
    
    lines = budget.lines if budget else []
    
    # Paginated Invoices
    invoices = []
    total_records = 0
    total_pages = 0
    
    if budget:
        query = db.query(Invoice).filter(Invoice.budget_id == budget.id)

        # Filters
        if status and status != 'all':
            query = query.filter(Invoice.status == status)
        
        if start_date:
            s_date = datetime.datetime.strptime(start_date, "%Y-%m-%d").date()
            query = query.filter(Invoice.issue_date >= s_date)
            
        if end_date:
            e_date = datetime.datetime.strptime(end_date, "%Y-%m-%d").date()
            query = query.filter(Invoice.issue_date <= e_date)

        # Count
        total_records = query.count()
        
        # Sorting
        if sort_by == 'invoice_number':
            column = Invoice.invoice_number
        elif sort_by == 'amount':
            column = Invoice.amount
        elif sort_by == 'status':
            column = Invoice.status
        elif sort_by == 'due_date':
            column = Invoice.due_date
        else:
            column = Invoice.issue_date # default

        if order == 'asc':
            query = query.order_by(column.asc())
        else:
            query = query.order_by(column.desc())

        # Fetch Page
        offset = (page - 1) * limit
        invoices = query.offset(offset).limit(limit).all()
            
        from math import ceil
        total_pages = ceil(total_records / limit)

    return templates.TemplateResponse("finance/detail.html", {
        "request": request,
        "user": user,
        "project": project,
        "budget": budget,
        "lines": lines,
        "invoices": invoices,
        "summary": status_data,
        "page": page,
        "total_pages": total_pages,
        "total_records": total_records,
        # Filters context
        "f_status": status,
        "f_start_date": start_date,
        "f_end_date": end_date,
        "sort_by": sort_by,
        "order": order
    })

@router.post("/{project_id}/invoice")
async def create_invoice(
    project_id: int, 
    invoice_number: str = Form(...),
    issue_date: str = Form(...),
    due_date: str = Form(...),
    amount: float = Form(...),
    budget_line_id: int = Form(...),
    db: Session = Depends(deps.get_db),
    user: User = Depends(deps.get_current_user)
):
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="Not authorized")

    project = db.query(Project).filter(Project.id == project_id).first()
    if not project or not project.budget:
        raise HTTPException(status_code=400, detail="Project or Budget not found")

    # Verify Line belongs to budget
    line = db.query(BudgetLine).filter(BudgetLine.id == budget_line_id, BudgetLine.budget_id == project.budget.id).first()
    if not line:
        raise HTTPException(status_code=400, detail="Invalid Budget Line")
        
    invoice = Invoice(
        budget_id=project.budget.id,
        budget_line_id=budget_line_id,
        invoice_number=invoice_number,
        issue_date=datetime.datetime.strptime(issue_date, "%Y-%m-%d").date(),
        due_date=datetime.datetime.strptime(due_date, "%Y-%m-%d").date(),
        amount=amount,
        status=InvoiceStatus.PENDING
    )
    db.add(invoice)
    db.commit()
    
    response = RedirectResponse(url=f"/finance/{project_id}", status_code=status.HTTP_303_SEE_OTHER)
    response.set_cookie(key="toast_message", value="Factura creada exitosamente")
    return response

@router.post("/invoice/{invoice_id}/pay")
async def pay_invoice(
    invoice_id: int,
    payment_date: str = Form(...),
    deposit_number: str = Form(...),
    amount: float = Form(...),
    payment_type: str = Form(...), # "full" or "partial"
    note: Optional[str] = Form(None),
    db: Session = Depends(deps.get_db),
    user: User = Depends(deps.get_current_user)
):
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="Not authorized")

    invoice = db.query(Invoice).filter(Invoice.id == invoice_id).first()
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")
        
    # Create Payment
    # Note: If partial payments are allowed multiple times, unique=True on Invoice relationship will fail.
    # Assuming for now 1 payment transaction per invoice based on current model.
    # If the user wants multiple partial payments, we'd need a bigger refactor.
    # Proceeding with current 1-to-1 constraint.
    
    # Check if payment already exists (if it's partial maybe we are updating? logic unclear from prompt but simplified model assumes new)
    if invoice.payment:
        # If exists, we might need to delete old or update. Let's error for safety or update.
        # Ideally we update the existing payment info.
        payment = invoice.payment
        payment.payment_date = datetime.datetime.strptime(payment_date, "%Y-%m-%d").date()
        payment.deposit_number = deposit_number
        payment.amount = amount
    else:
        payment = Payment(
            invoice_id=invoice.id,
            payment_date=datetime.datetime.strptime(payment_date, "%Y-%m-%d").date(),
            deposit_number=deposit_number,
            amount=amount
        )
        db.add(payment)
    
    # Update Invoice Status and Note
    if payment_type == "partial":
        invoice.status = InvoiceStatus.PARTIAL
        if not note: 
             # Ideally require it, but for robustness allow empty if client didn't send
             pass
    else:
        invoice.status = InvoiceStatus.PAID
    
    if note:
        invoice.note = note
    
    db.commit()
    
    response = RedirectResponse(url=f"/finance/{invoice.budget.project_id}", status_code=status.HTTP_303_SEE_OTHER)
    msg = "Pago registrado exitosamente" if payment_type == "full" else "Pago parcial registrado"
    response.set_cookie(key="toast_message", value=msg)
    return response
