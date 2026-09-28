from typing import Optional
from fastapi import APIRouter, Depends, Request, HTTPException, status, Form
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
from sqlalchemy import func
import datetime

from app.db.models.project import Project
from app.db.models.finance import ProjectBudget, BudgetLine, Invoice, Payment, InvoiceStatus, ProjectCost
from app.db.models.schedule import ProjectSchedule
from app.db.models.user import User
from app.db.models.associations import project_users
from app.db.models.payroll import PayrollEntry, PayrollPeriod
from app.routers import deps
from app.core.roles import ADMIN, CLIENT, FINANCE_ROLES, OPERATIONS_ROLES
from app.utils.activity import log_activity, compute_diff

router = APIRouter(
    prefix="/finance",
    tags=["finance"],
    dependencies=[Depends(deps.require_roles(*OPERATIONS_ROLES))]
)

from app.core.templates import templates

def check_finance_access(user: User):
    if user.role not in FINANCE_ROLES:
        raise HTTPException(status_code=403, detail="Forbidden")


def error_redirect(url: str, message: str):
    response = RedirectResponse(url=url, status_code=status.HTTP_303_SEE_OTHER)
    response.set_cookie(key="toast_message", value=message)
    response.set_cookie(key="toast_type", value="error")
    return response


def schedule_payroll_cost(db: Session, schedules, periods) -> dict:
    """Company cost of confirmed schedules that fall in final payrolls, per period id, with the
    hourly rate frozen in that payroll (the person's current rate for payrolls made before)."""
    rates = {(e.payroll_period_id, e.user_id): e.hourly_rate
             for e in db.query(PayrollEntry).filter(PayrollEntry.payroll_period_id.in_([p.id for p in periods]))}
    costs = {}
    for sched in schedules:
        period = next((p for p in periods if p.start_date <= sched.date <= p.end_date), None)
        if not period or not sched.user:
            continue
        rate = rates.get((period.id, sched.user_id))
        if rate is None:
            rate = sched.user.hourly_rate or 0.0
        gross = (sched.hours_worked or 0.0) * rate + (sched.overtime_hours or 0.0) * rate * 1.5
        # Gross + 26.67% CCSS + 18% previsiones = company cost
        costs[period.id] = costs.get(period.id, 0.0) + gross * 1.4467
    return costs


def line_available(db: Session, line: BudgetLine, exclude_invoice_id: Optional[int] = None) -> float:
    """What is still left to invoice on a budget line (its total minus its invoices)."""
    query = db.query(func.coalesce(func.sum(Invoice.amount), 0.0)).filter(Invoice.budget_line_id == line.id)
    if exclude_invoice_id:
        query = query.filter(Invoice.id != exclude_invoice_id)
    return line.total - (query.scalar() or 0.0)


def over_line_message(line: BudgetLine, available: float) -> str:
    return (f"La factura supera lo que queda por facturar en «{line.name}» ({available:,.2f}). "
            "Si es correcto (por ejemplo, una prórroga), confirmalo en la ventana.")

def get_project_budget_status(db: Session, project: Project):
    # Calculate totals
    budget = db.query(ProjectBudget).filter(ProjectBudget.project_id == project.id).first()
    
    total_adjudicated = 0.0
    total_invoiced = 0.0
    total_paid = 0.0
    
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
            if inv.payment:
                total_paid += inv.payment.amount + (inv.payment.retention_amount or 0.0)

    # Calculate manual costs
    manual_costs_query = db.query(func.sum(ProjectCost.amount)).filter(ProjectCost.project_id == project.id).scalar()
    manual_costs = manual_costs_query or 0.0

    # Calculate payroll costs
    # Gross salary = hours * rate. Company cost assumed + 44.67% approx or standard 26.67% + 18%.
    # For simplicity of metric tracking, we calculate direct worker gross + 26.67% CCSS cost:
    confirmed_schedules = db.query(ProjectSchedule).filter(
        ProjectSchedule.project_id == project.id,
        ProjectSchedule.is_confirmed == True
    ).all()
    final_periods = db.query(PayrollPeriod).filter(PayrollPeriod.status == "final").all()
    payroll_costs = sum(schedule_payroll_cost(db, confirmed_schedules, final_periods).values())

    total_costs = manual_costs + payroll_costs

    return {
        "budget": budget,
        "total_adjudicated": total_adjudicated,
        "total_invoiced": total_invoiced,
        "total_paid": total_paid,
        "balance": total_adjudicated - total_invoiced,  # still to invoice
        "receivable": total_invoiced - total_paid,       # invoiced, not yet collected
        "total_costs": total_costs
    }

def check_update_overdue_invoices(db: Session, project_id: Optional[int] = None):
    """Pending invoices past their due date become overdue (all projects when project_id is None)."""
    from app.utils.timecr import today_cr
    query = db.query(Invoice).join(ProjectBudget).filter(
        Invoice.status == InvoiceStatus.PENDING,
        Invoice.due_date < today_cr()
    )
    if project_id is not None:
        query = query.filter(ProjectBudget.project_id == project_id)
    overdue = query.all()
    
    if overdue:
        for inv in overdue:
            inv.status = InvoiceStatus.OVERDUE
        db.commit()

@router.get("/")
def finance_dashboard(request: Request, db: Session = Depends(deps.get_db), user: User = Depends(deps.get_current_user)):
    check_finance_access(user)
    
    # Get Projects
    if user.role == ADMIN:
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
            "receivable": status["receivable"],
            "total_costs": status["total_costs"]
        })

    return templates.TemplateResponse("finance/index.html", {
        "request": request, 
        "user": user, 
        "projects": finance_projects
    })

@router.get("/{project_id}")
def finance_detail(
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

    if user.role == CLIENT and user.id not in [u.id for u in project.users]:
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

    # The client only sees invoices and payments: no costs, payroll or margin.
    internal = user.role != CLIENT
    lines_data = [{"line": l, "available": line_available(db, l)} for l in lines]

    # Fetch manuals project costs to display in Detail view
    costs = [] if not internal else db.query(ProjectCost).filter(ProjectCost.project_id == project.id).order_by(ProjectCost.date.desc()).all()

    # Calculate detailed payroll to display Grouped by Period
    payroll_details = []
    
    payroll_periods = db.query(PayrollPeriod).filter(PayrollPeriod.status == 'final').order_by(PayrollPeriod.start_date.desc()).all()
    
    confirmed_schedules = db.query(ProjectSchedule).filter(
        ProjectSchedule.project_id == project.id,
        ProjectSchedule.is_confirmed == True
    ).all()
    
    period_costs = schedule_payroll_cost(db, confirmed_schedules, payroll_periods) if internal else {}
    for period in payroll_periods if internal else []:
        if period.id in period_costs:
            payroll_details.append({
                "period_str": f"{period.start_date.strftime('%d/%m/%Y')} - {period.end_date.strftime('%d/%m/%Y')}",
                "start_date": period.start_date,
                "status": period.status,
                "cost": period_costs[period.id]
            })

    payroll_details.sort(key=lambda x: x['start_date'], reverse=True)

    # Fetch Retentions associated with this project's invoices
    retentions = [] if not internal else db.query(Payment)\
        .join(Invoice)\
        .join(ProjectBudget)\
        .filter(ProjectBudget.project_id == project.id, Payment.retention_amount > 0)\
        .order_by(Payment.payment_date.desc())\
        .all()

    return  templates.TemplateResponse("finance/detail.html", {
        "request": request,
        "user": user,
        "project": project,
        "budget": budget,
        "lines": lines,
        "lines_data": lines_data,
        "internal": internal,
        "invoices": invoices,
        "costs": costs,
        "retentions": retentions,
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
def create_invoice(
    project_id: int, 
    invoice_number: str = Form(...),
    issue_date: str = Form(...),
    due_date: str = Form(...),
    amount: float = Form(...),
    budget_line_id: int = Form(...),
    confirm_over: bool = Form(False),
    db: Session = Depends(deps.get_db),
    user: User = Depends(deps.get_current_user)
):
    if user.role != ADMIN:
        raise HTTPException(status_code=403, detail="Not authorized")

    project = db.query(Project).filter(Project.id == project_id).first()
    if not project or not project.budget:
        raise HTTPException(status_code=400, detail="Project or Budget not found")

    # Verify Line belongs to budget
    line = db.query(BudgetLine).filter(BudgetLine.id == budget_line_id, BudgetLine.budget_id == project.budget.id).first()
    if not line:
        raise HTTPException(status_code=400, detail="Invalid Budget Line")
    available = line_available(db, line)
    if amount > available + 0.005 and not confirm_over:
        return error_redirect(f"/finance/{project_id}", over_line_message(line, available))

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
def edit_invoice(
    invoice_id: int, 
    invoice_number: str = Form(...),
    issue_date: str = Form(...),
    due_date: str = Form(...),
    amount: float = Form(...),
    budget_line_id: int = Form(...),
    confirm_over: bool = Form(False),
    db: Session = Depends(deps.get_db),
    user: User = Depends(deps.get_current_user)
):
    if user.role != ADMIN:
        raise HTTPException(status_code=403, detail="Not authorized")

    invoice = db.query(Invoice).filter(Invoice.id == invoice_id).first()
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")

    # Verify new line belongs to budget
    line = db.query(BudgetLine).filter(BudgetLine.id == budget_line_id, BudgetLine.budget_id == invoice.budget_id).first()
    if not line:
        raise HTTPException(status_code=400, detail="Invalid Budget Line")
    available = line_available(db, line, exclude_invoice_id=invoice.id)
    if amount > available + 0.005 and not confirm_over:
        return error_redirect(f"/finance/{invoice.budget.project_id}", over_line_message(line, available))

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
def delete_invoice(
    invoice_id: int, 
    db: Session = Depends(deps.get_db),
    user: User = Depends(deps.get_current_user)
):
    if user.role != ADMIN:
        raise HTTPException(status_code=403, detail="Not authorized")

    invoice = db.query(Invoice).filter(Invoice.id == invoice_id).first()
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")

    project_id = invoice.budget.project_id
    
    # An invoice with payments can't be deleted: the payment would be left without its invoice.
    if invoice.payment or invoice.status not in (InvoiceStatus.PENDING, InvoiceStatus.OVERDUE):
        return error_redirect(f"/finance/{project_id}",
                              f"La factura #{invoice.invoice_number} ya tiene pagos registrados y no se puede eliminar.")

    number = invoice.invoice_number
    db.delete(invoice)
    db.commit()
    log_activity(db, user, "BORRAR", "Factura", invoice_id, f"Eliminó la factura #{number}")
    
    response = RedirectResponse(url=f"/finance/{project_id}", status_code=status.HTTP_303_SEE_OTHER)
    response.set_cookie(key="toast_message", value="Factura eliminada")
    return response

@router.post("/{project_id}/cost")
def create_cost(
    project_id: int, 
    date: str = Form(...),
    description: str = Form(...),
    amount: float = Form(...),
    db: Session = Depends(deps.get_db),
    user: User = Depends(deps.get_current_user)
):
    if user.role != ADMIN:
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
def edit_cost(
    cost_id: int, 
    date: str = Form(...),
    description: str = Form(...),
    amount: float = Form(...),
    db: Session = Depends(deps.get_db),
    user: User = Depends(deps.get_current_user)
):
    if user.role != ADMIN:
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
def delete_cost(
    cost_id: int, 
    db: Session = Depends(deps.get_db),
    user: User = Depends(deps.get_current_user)
):
    if user.role != ADMIN:
        raise HTTPException(status_code=403, detail="Not authorized")

    cost = db.query(ProjectCost).filter(ProjectCost.id == cost_id).first()
    if not cost:
        raise HTTPException(status_code=404, detail="Cost not found")

    project_id = cost.project_id
    details = f"Eliminó el gasto «{cost.description}» por {cost.amount:,.2f}"
    db.delete(cost)
    db.commit()
    log_activity(db, user, "BORRAR", "Gasto", cost_id, details)
    
    response = RedirectResponse(url=f"/finance/{project_id}", status_code=status.HTTP_303_SEE_OTHER)
    response.set_cookie(key="toast_message", value="Costo eliminado")
    return response

@router.post("/invoice/{invoice_id}/pay")
def pay_invoice(
    invoice_id: int,
    payment_date: str = Form(...),
    deposit_number: str = Form(...),
    amount: float = Form(...),
    retention_amount: Optional[float] = Form(0.0),
    payment_type: str = Form(...), # "full" or "partial"
    note: Optional[str] = Form(None),
    db: Session = Depends(deps.get_db),
    user: User = Depends(deps.get_current_user)
):
    if user.role != ADMIN:
        raise HTTPException(status_code=403, detail="Not authorized")

    invoice = db.query(Invoice).filter(Invoice.id == invoice_id).first()
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")
        
    old_data = {
        "estado_factura": invoice.status.value,
        "fecha_pago": "Ninguna" if not invoice.payment else str(invoice.payment.payment_date),
        "monto_abonado": 0.0 if not invoice.payment else invoice.payment.amount
    }
        
    # One Payment row per invoice holds the running total: a later payment of a partially
    # paid invoice adds to it (amounts, retention, receipt numbers) instead of replacing it.
    paid_on = datetime.datetime.strptime(payment_date, "%Y-%m-%d").date()
    retention_amount = retention_amount or 0.0
    if invoice.payment:
        payment = invoice.payment
        payment.amount = (payment.amount or 0.0) + amount
        payment.retention_amount = (payment.retention_amount or 0.0) + retention_amount
        payment.payment_date = paid_on
        receipts = [r.strip() for r in (payment.deposit_number or "").split(",") if r.strip()]
        if deposit_number.strip() and deposit_number.strip() not in receipts:
            receipts.append(deposit_number.strip())
        payment.deposit_number = ", ".join(receipts)
    else:
        payment = Payment(invoice_id=invoice.id, payment_date=paid_on, deposit_number=deposit_number,
                          amount=amount, retention_amount=retention_amount)
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
        # Each partial payment keeps its note, with the date.
        entry = f"{paid_on:%d/%m/%Y}: {note.strip()}"
        invoice.note = f"{invoice.note}\n{entry}" if invoice.note and old_data["fecha_pago"] != "Ninguna" else entry
    
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
