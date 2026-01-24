from typing import List, Optional
from datetime import date
from fastapi import APIRouter, Depends, Query, HTTPException, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session, joinedload

from app.db.session import SessionLocal
from app.routers import deps
from app.db.models.user import User
from app.db.models.project import Project
from app.db.models.finance import ProjectBudget, BudgetLine, Invoice

router = APIRouter(
    prefix="/finance",
    tags=["finance"],
    dependencies=[Depends(deps.get_current_user)]
)

templates = Jinja2Templates(directory="app/templates")

# --- Middleware / Dependency ---
async def require_finance_access(user: User = Depends(deps.get_current_user)):
    if user.role == "worker":
        raise HTTPException(status_code=403, detail="Acceso denegado")
    return user

async def require_admin(user: User = Depends(deps.get_current_user)):
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="Requiere privilegios de administrador")
    return user

# --- Dashboard ---
@router.get("/", response_class=HTMLResponse)
async def finance_dashboard(
    request: Request,
    db: Session = Depends(deps.get_db),
    user: User = Depends(require_finance_access)
):
    # Filter projects based on role
    query = db.query(Project).filter(Project.is_active == True)
    
    if user.role == "client":
        # Ensure client can only see their projects
        # Logic depends on how projects are linked to clients.
        # Assuming Project has 'users' relationship or strict check.
        # Previous modules used project_users association.
        query = query.filter(Project.users.any(id=user.id))
    
    projects = query.options(joinedload(Project.budget).joinedload(ProjectBudget.invoices)).all()
    
    # Pre-calculate totals for dashboard display to avoid heavy logic in template
    dashboard_data = []
    for p in projects:
        budget = p.budget
        total_adjudicated = 0
        total_invoiced = 0
        
        if budget:
            # We need to load lines to calc total_adjudicated
            # Or use sql sum. Python sum is fine for reasonable size.
            # Lazy load lines
            lines = db.query(BudgetLine).filter(BudgetLine.budget_id == budget.id).all()
            total_adjudicated = sum([(l.subtotal + (l.subtotal * (l.tax_percentage/100.0))) for l in lines])
            
            # Invoices
            invoices = db.query(Invoice).filter(Invoice.budget_id == budget.id).all()
            total_invoiced = sum([i.amount for i in invoices])
        
        dashboard_data.append({
            "project": p,
            "budget": budget,
            "total_adjudicated": total_adjudicated,
            "total_invoiced": total_invoiced,
            "balance": total_adjudicated - total_invoiced
        })

    return templates.TemplateResponse("finance/index.html", {
        "request": request,
        "user": user,
        "data": dashboard_data
    })


# --- Project Budget Detail ---
@router.get("/project/{project_id}", response_class=HTMLResponse)
async def finance_detail(
    project_id: int,
    request: Request,
    db: Session = Depends(deps.get_db),
    user: User = Depends(require_finance_access)
):
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Proyecto no encontrado")

    # Security check for client
    if user.role == "client":
        if user not in project.users:
             raise HTTPException(status_code=403, detail="No tiene acceso a este proyecto")

    # Ensure budget exists or create empty one? 
    # Usually better to create on first access or explicitly.
    # Let's auto-create empty if not exists for convenience, or handle None in template.
    # Auto-creating makes logic easier.
    if not project.budget:
        new_budget = ProjectBudget(project_id=project.id)
        db.add(new_budget)
        db.commit()
        db.refresh(project)

    budget = project.budget
    lines = db.query(BudgetLine).filter(BudgetLine.budget_id == budget.id).all()
    invoices = db.query(Invoice).filter(Invoice.budget_id == budget.id).order_by(Invoice.date_issued.desc()).all()

    # Calculations
    grand_total_adjudicated = 0.0
    for l in lines:
        l.tax_amount = l.subtotal * (l.tax_percentage / 100.0)
        l.total_line = l.subtotal + l.tax_amount
        grand_total_adjudicated += l.total_line
    
    grand_total_invoiced = sum([i.amount for i in invoices])
    balance = grand_total_adjudicated - grand_total_invoiced

    return templates.TemplateResponse("finance/detail.html", {
        "request": request,
        "user": user,
        "project": project,
        "budget": budget,
        "lines": lines,
        "invoices": invoices,
        "stats": {
            "adjudicated": grand_total_adjudicated,
            "invoiced": grand_total_invoiced,
            "balance": balance
        }
    })


# --- Update Budget Info (Admin) ---
@router.post("/project/{project_id}/update")
async def update_budget_info(
    project_id: int,
    licitation_number: str = Form(None),
    contract_duration: str = Form(None),
    is_prorrogable: bool = Form(False),
    prorrogable_time: str = Form(None),
    prorrogable_amount: float = Form(None),
    next_url: str = Form(None),
    db: Session = Depends(deps.get_db),
    user: User = Depends(require_admin)
):
    budget = db.query(ProjectBudget).filter(ProjectBudget.project_id == project_id).first()
    if not budget:
        raise HTTPException(404, "Budget not found")
    
    budget.licitation_number = licitation_number
    budget.contract_duration = contract_duration
    budget.is_prorrogable = is_prorrogable
    budget.prorrogable_time = prorrogable_time if is_prorrogable else None
    budget.prorrogable_amount = prorrogable_amount if is_prorrogable else None
    
    db.commit()
    db.commit()
    redirect = next_url if next_url else f"/finance/project/{project_id}"
    return RedirectResponse(url=redirect, status_code=303)


# --- Line Items CRUD (Admin) ---
@router.post("/project/{project_id}/line")
async def upsert_line(
    project_id: int,
    line_id: int = Form(None),
    name: str = Form(...),
    subtotal: float = Form(...),
    tax_percentage: float = Form(13.0),
    next_url: str = Form(None),
    db: Session = Depends(deps.get_db),
    user: User = Depends(require_admin)
):
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project or not project.budget:
        raise HTTPException(404, "Budget not found")
        
    if line_id:
        line = db.query(BudgetLine).filter(BudgetLine.id == line_id, BudgetLine.budget_id == project.budget.id).first()
        if not line:
            raise HTTPException(404, "Line not found")
        line.name = name
        line.subtotal = subtotal
        line.tax_percentage = tax_percentage
    else:
        new_line = BudgetLine(
            budget_id=project.budget.id,
            name=name,
            subtotal=subtotal,
            tax_percentage=tax_percentage
        )
        db.add(new_line)
    
    db.commit()
    db.commit()
    redirect = next_url if next_url else f"/finance/project/{project_id}"
    return RedirectResponse(url=redirect, status_code=303)

@router.post("/line/{line_id}/delete")
async def delete_line(
    line_id: int,
    next_url: str = Query(None),
    db: Session = Depends(deps.get_db),
    user: User = Depends(require_admin)
):
    line = db.query(BudgetLine).filter(BudgetLine.id == line_id).first()
    if not line:
        raise HTTPException(404, "Line not found")
        
    project_id = line.budget.project_id
    db.delete(line)
    db.commit()
    db.commit()
    redirect = next_url if next_url else f"/finance/project/{project_id}"
    return RedirectResponse(url=redirect, status_code=303)


# --- Invoice CRUD (Admin) ---
@router.post("/project/{project_id}/invoice")
async def upsert_invoice(
    project_id: int,
    invoice_id: int = Form(None),
    line_id: int = Form(...),
    date_issued: str = Form(...),
    invoice_number: str = Form(...),
    amount: float = Form(...),
    due_date: str = Form(...),
    db: Session = Depends(deps.get_db),
    user: User = Depends(require_admin)
):
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project or not project.budget:
         raise HTTPException(404, "Budget not found")

    if invoice_id:
        invoice = db.query(Invoice).filter(Invoice.id == invoice_id).first()
        if not invoice:
            raise HTTPException(404, "Invoice not found")
        invoice.line_id = line_id
        invoice.date_issued = date.fromisoformat(date_issued)
        invoice.invoice_number = invoice_number
        invoice.amount = amount
        invoice.due_date = date.fromisoformat(due_date)
    else:
        new_invoice = Invoice(
            budget_id=project.budget.id,
            line_id=line_id,
            date_issued=date.fromisoformat(date_issued),
            invoice_number=invoice_number,
            amount=amount,
            due_date=date.fromisoformat(due_date)
        )
        db.add(new_invoice)
    
    db.commit()
    return RedirectResponse(url=f"/finance/project/{project_id}", status_code=303)


@router.post("/invoice/{invoice_id}/pay")
async def pay_invoice(
    invoice_id: int,
    payment_date: str = Form(...),
    deposit_number: str = Form(None),
    paid_amount: float = Form(...),
    db: Session = Depends(deps.get_db),
    user: User = Depends(require_admin)
):
    invoice = db.query(Invoice).filter(Invoice.id == invoice_id).first()
    if not invoice:
        raise HTTPException(404, "Invoice not found")
    
    invoice.payment_date = date.fromisoformat(payment_date)
    # If deposit number is optional, handle empty
    invoice.deposit_number = deposit_number
    invoice.paid_amount = paid_amount
    
    db.commit()
    return RedirectResponse(url=f"/finance/project/{invoice.budget.project_id}", status_code=303)

@router.post("/invoice/{invoice_id}/delete")
async def delete_invoice(
    invoice_id: int,
    db: Session = Depends(deps.get_db),
    user: User = Depends(require_admin)
):
    invoice = db.query(Invoice).filter(Invoice.id == invoice_id).first()
    if not invoice:
        raise HTTPException(404, "Invoice not found")
        
    project_id = invoice.budget.project_id
    db.delete(invoice)
    db.commit()
    return RedirectResponse(url=f"/finance/project/{project_id}", status_code=303)
