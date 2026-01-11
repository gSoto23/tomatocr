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
async def finance_detail(project_id: int, request: Request, db: Session = Depends(deps.get_db), user: User = Depends(deps.get_current_user)):
    check_finance_access(user)
    
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
         raise HTTPException(status_code=404, detail="Project not found")

    if user.role == "client" and user.id not in [u.id for u in project.users]:
        raise HTTPException(status_code=403, detail="Not authorized")

    status_data = get_project_budget_status(db, project)
    budget = status_data["budget"]
    
    lines = budget.lines if budget else []
    invoices = budget.invoices if budget else []

    # Sort invoices by date desc
    invoices.sort(key=lambda x: x.issue_date, reverse=True)

    return templates.TemplateResponse("finance/detail.html", {
        "request": request,
        "user": user,
        "project": project,
        "budget": budget,
        "lines": lines,
        "invoices": invoices,
        "summary": status_data
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
    db: Session = Depends(deps.get_db),
    user: User = Depends(deps.get_current_user)
):
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="Not authorized")

    invoice = db.query(Invoice).filter(Invoice.id == invoice_id).first()
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")
        
    # Create Payment
    payment = Payment(
        invoice_id=invoice.id,
        payment_date=datetime.datetime.strptime(payment_date, "%Y-%m-%d").date(),
        deposit_number=deposit_number,
        amount=amount
    )
    db.add(payment)
    
    # Update Invoice Status
    invoice.status = InvoiceStatus.PAID
    
    db.commit()
    
    response = RedirectResponse(url=f"/finance/{invoice.budget.project_id}", status_code=status.HTTP_303_SEE_OTHER)
    response.set_cookie(key="toast_message", value="Pago registrado exitosamente")
    return response
