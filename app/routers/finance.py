from typing import List, Optional
from fastapi import APIRouter, Depends, Request, HTTPException, status, Form
from fastapi.responses import RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from sqlalchemy import func
import datetime

from app.db.session import SessionLocal
from app.db.models.project import Project
from app.db.models.finance import ProjectBudget, BudgetLine, Invoice, Payment, InvoiceStatus, ProjectCost
from app.db.models.schedule import ProjectSchedule
from app.db.models.user import User
from app.db.models.associations import project_users
from app.db.models.payroll import PayrollPeriod
from app.routers import deps
from app.utils.activity import log_activity, compute_diff

router = APIRouter(
    prefix="/finance",
    tags=["finance"],
    dependencies=[Depends(deps.get_current_user)]
)

from app.core.templates import templates

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

    # Calculate manual costs
    manual_costs_query = db.query(func.sum(ProjectCost.amount)).filter(ProjectCost.project_id == project.id).scalar()
    manual_costs = manual_costs_query or 0.0

    # Calculate payroll costs
    # Gross salary = hours * rate. Company cost assumed + 44.67% approx or standard 26.67% + 18%.
    # For simplicity of metric tracking, we calculate direct worker gross + 26.67% CCSS cost:
    payroll_costs = 0.0
    confirmed_schedules = db.query(ProjectSchedule).filter(
        ProjectSchedule.project_id == project.id,
        ProjectSchedule.is_confirmed == True
    ).all()
    
    final_periods = db.query(PayrollPeriod).filter(PayrollPeriod.status == "final").all()
    final_ranges = [(p.start_date, p.end_date) for p in final_periods]

    for sched in confirmed_schedules:
        if any(start <= sched.date <= end for start, end in final_ranges):
            if sched.user and getattr(sched.user, 'hourly_rate', None):
                worker_rate = sched.user.hourly_rate
                regular_pay = (sched.hours_worked or 0.0) * worker_rate
                overtime_pay = (sched.overtime_hours or 0.0) * worker_rate * 1.5
                gross = regular_pay + overtime_pay
                
                # Gross + 26.67% CCSS + 18% Previsiones = Total Company Cost
                company_cost = gross * 1.4467
                payroll_costs += company_cost

    total_costs = manual_costs + payroll_costs

    return {
        "budget": budget,
        "total_adjudicated": total_adjudicated,
        "total_invoiced": total_invoiced,
        "balance": total_adjudicated - total_invoiced,
        "total_costs": total_costs
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
            "balance": status["balance"],
            "total_costs": status["total_costs"]
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

    # Fetch manuals project costs to display in Detail view
    costs = db.query(ProjectCost).filter(ProjectCost.project_id == project.id).order_by(ProjectCost.date.desc()).all()

    # Calculate detailed payroll to display Grouped by Period
    payroll_details = []
    
    payroll_periods = db.query(PayrollPeriod).filter(PayrollPeriod.status == 'final').order_by(PayrollPeriod.start_date.desc()).all()
    
    confirmed_schedules = db.query(ProjectSchedule).filter(
        ProjectSchedule.project_id == project.id,
        ProjectSchedule.is_confirmed == True
    ).all()
    
    for period in payroll_periods:
        period_cost = 0.0
        # Find schedules in this period
        schedules_in_period = [s for s in confirmed_schedules if period.start_date <= s.date <= period.end_date]
        
        if schedules_in_period:
            for sched in schedules_in_period:
                if sched.user and getattr(sched.user, 'hourly_rate', None):
                    worker_rate = sched.user.hourly_rate
                    regular_pay = (sched.hours_worked or 0.0) * worker_rate
                    overtime_pay = (sched.overtime_hours or 0.0) * worker_rate * 1.5
                    gross = regular_pay + overtime_pay
                    period_cost += gross * 1.4467
            
            payroll_details.append({
                "period_str": f"{period.start_date.strftime('%d/%m/%Y')} - {period.end_date.strftime('%d/%m/%Y')}",
                "start_date": period.start_date,
                "status": period.status,
                "cost": period_cost
            })
        
    payroll_details.sort(key=lambda x: x['start_date'], reverse=True)

    return  templates.TemplateResponse("finance/detail.html", {
        "request": request,
        "user": user,
        "project": project,
        "budget": budget,
        "lines": lines,
        "invoices": invoices,
        "costs": costs,
        "payroll_details": payroll_details,
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
    db.refresh(invoice)
    
    log_activity(
        db=db, user=user, action="CREAR", entity_type="Factura", entity_id=invoice.id, 
        details=f"Factura #{invoice_number} por ${amount:,.2f} en presupuesto de {project.name}"
    )
    
    response = RedirectResponse(url=f"/finance/{project_id}", status_code=status.HTTP_303_SEE_OTHER)
    response.set_cookie(key="toast_message", value="Factura creada exitosamente")
    return response

@router.post("/invoice/{invoice_id}/edit")
async def edit_invoice(
    invoice_id: int, 
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

    invoice = db.query(Invoice).filter(Invoice.id == invoice_id).first()
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")

    # Verify new line belongs to budget
    line = db.query(BudgetLine).filter(BudgetLine.id == budget_line_id, BudgetLine.budget_id == invoice.budget_id).first()
    if not line:
        raise HTTPException(status_code=400, detail="Invalid Budget Line")

    old_data = {
        "monto": invoice.amount,
        "fecha_emision": str(invoice.issue_date),
        "fecha_vencimiento": str(invoice.due_date),
        "numero": invoice.invoice_number
    }

    invoice.invoice_number = invoice_number
    invoice.issue_date = datetime.datetime.strptime(issue_date, "%Y-%m-%d").date()
    invoice.due_date = datetime.datetime.strptime(due_date, "%Y-%m-%d").date()
    invoice.amount = amount
    invoice.budget_line_id = budget_line_id
    db.commit()
    
    new_data = {
        "monto": invoice.amount,
        "fecha_emision": str(invoice.issue_date),
        "fecha_vencimiento": str(invoice.due_date),
        "numero": invoice.invoice_number
    }
    
    diffs = compute_diff(old_data, new_data)
    if diffs:
        log_activity(db, user, "EDITAR", "Factura", invoice.id, {"cambios": diffs, "mensaje": f"Factura #{invoice_number} modificada"})
    
    response = RedirectResponse(url=f"/finance/{invoice.budget.project_id}", status_code=status.HTTP_303_SEE_OTHER)
    response.set_cookie(key="toast_message", value="Factura actualizada exitosamente")
    return response

@router.post("/invoice/{invoice_id}/delete")
async def delete_invoice(
    invoice_id: int, 
    db: Session = Depends(deps.get_db),
    user: User = Depends(deps.get_current_user)
):
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="Not authorized")

    invoice = db.query(Invoice).filter(Invoice.id == invoice_id).first()
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")

    project_id = invoice.budget.project_id
    
    # Optional: ensure we can delete it (e.g., if it has payments?)
    if invoice.status != InvoiceStatus.PENDING and invoice.status != InvoiceStatus.OVERDUE:
        raise HTTPException(status_code=400, detail="Cannot delete invoice with payments")

    db.delete(invoice)
    db.commit()
    
    response = RedirectResponse(url=f"/finance/{project_id}", status_code=status.HTTP_303_SEE_OTHER)
    response.set_cookie(key="toast_message", value="Factura eliminada")
    return response

@router.post("/{project_id}/cost")
async def create_cost(
    project_id: int, 
    date: str = Form(...),
    description: str = Form(...),
    amount: float = Form(...),
    db: Session = Depends(deps.get_db),
    user: User = Depends(deps.get_current_user)
):
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="Not authorized")

    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=400, detail="Project not found")

    cost = ProjectCost(
        project_id=project.id,
        date=datetime.datetime.strptime(date, "%Y-%m-%d").date(),
        description=description,
        amount=amount
    )
    db.add(cost)
    db.commit()
    
    response = RedirectResponse(url=f"/finance/{project_id}", status_code=status.HTTP_303_SEE_OTHER)
    response.set_cookie(key="toast_message", value="Costo registrado exitosamente")
    return response

@router.post("/cost/{cost_id}/edit")
async def edit_cost(
    cost_id: int, 
    date: str = Form(...),
    description: str = Form(...),
    amount: float = Form(...),
    db: Session = Depends(deps.get_db),
    user: User = Depends(deps.get_current_user)
):
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="Not authorized")

    cost = db.query(ProjectCost).filter(ProjectCost.id == cost_id).first()
    if not cost:
        raise HTTPException(status_code=404, detail="Cost not found")

    cost.date = datetime.datetime.strptime(date, "%Y-%m-%d").date()
    cost.description = description
    cost.amount = amount
    db.commit()
    
    response = RedirectResponse(url=f"/finance/{cost.project_id}", status_code=status.HTTP_303_SEE_OTHER)
    response.set_cookie(key="toast_message", value="Costo actualizado exitosamente")
    return response

@router.post("/cost/{cost_id}/delete")
async def delete_cost(
    cost_id: int, 
    db: Session = Depends(deps.get_db),
    user: User = Depends(deps.get_current_user)
):
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="Not authorized")

    cost = db.query(ProjectCost).filter(ProjectCost.id == cost_id).first()
    if not cost:
        raise HTTPException(status_code=404, detail="Cost not found")

    project_id = cost.project_id
    db.delete(cost)
    db.commit()
    
    response = RedirectResponse(url=f"/finance/{project_id}", status_code=status.HTTP_303_SEE_OTHER)
    response.set_cookie(key="toast_message", value="Costo eliminado")
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
        
    old_data = {
        "estado_factura": invoice.status.value,
        "fecha_pago": "Ninguna" if not invoice.payment else str(invoice.payment.payment_date),
        "monto_abonado": 0.0 if not invoice.payment else invoice.payment.amount
    }
        
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
    
    new_data = {
        "estado_factura": invoice.status.value,
        "monto_abonado": payment.amount,
        "fecha_pago": str(payment.payment_date)
    }
    
    db.commit()
    
    diffs = compute_diff(old_data, new_data)
    msg = f"Pago {'Parcial' if payment_type == 'partial' else 'Total'} a Factura #{invoice.invoice_number}"
    log_activity(db, user, "PAGO", "Factura", invoice.id, {"cambios": diffs, "mensaje": msg})
    
    response = RedirectResponse(url=f"/finance/{invoice.budget.project_id}", status_code=status.HTTP_303_SEE_OTHER)
    msg = "Pago registrado exitosamente" if payment_type == "full" else "Pago parcial registrado"
    response.set_cookie(key="toast_message", value=msg)
    return response
