"""Sellers' commissions (docs/PLAN_PLANILLA_CALENDARIO.md, Fase 5).

- When an invoice becomes PAGADA, its seller earns a % of its amount without IVA.
- When the first invoice of a "Nuevo" opportunity is paid, the seller earns the new-client amount.
- The seller is the owner of the opportunity that made the project (or of the account).
- Each commission becomes a payroll adjustment, so it joins the seller's next payroll and the
  record says which payroll paid it. Cancelling one before it is paid removes it; after, a
  negative adjustment takes it back in the next payroll.
"""
from datetime import date, datetime, timezone
from typing import List, Optional

from sqlalchemy.orm import Session

from app.core.roles import ADMIN
from app.db.models.commission import Commission
from app.db.models.crm import Account, CrmSetting, Opportunity
from app.db.models.finance import Invoice
from app.db.models.payroll import PayrollAdjustment
from app.db.models.project import Project
from app.db.models.user import User
from app.utils.planilla import recompute

GENERAL_KEYS = {"percent": "commission_percent", "new_client": "commission_new_client"}
KINDS = {"factura": "Factura cobrada", "cliente_nuevo": "Cliente nuevo"}
STATUS_LABELS = {"pendiente": "Para la próxima planilla", "borrador": "En planilla (borrador)",
                 "pagada": "Pagada", "anulada": "Anulada", "revertida": "Revertida"}


def general_rules(db: Session) -> dict:
    """The general % per invoice and amount per new client (0 until the admin sets them)."""
    rules = {}
    for name, key in GENERAL_KEYS.items():
        row = db.get(CrmSetting, key)
        try:
            rules[name] = max(0.0, float(row.value)) if row and row.value else 0.0
        except ValueError:
            rules[name] = 0.0
    return rules


def set_general_rules(db: Session, percent: float, new_client: float) -> None:
    for name, value in (("percent", percent), ("new_client", new_client)):
        key = GENERAL_KEYS[name]
        row = db.get(CrmSetting, key) or CrmSetting(key=key)
        row.value = str(max(0.0, value or 0.0))
        db.add(row)


def rules_for(db: Session, person: Optional[User]) -> dict:
    """The person's own rules where set; otherwise the general ones, only for people who sell
    (ventas and supervisors marked "También vende"). An admin earns only with their own."""
    if not person:
        return {"percent": 0.0, "new_client": 0.0}
    general = general_rules(db) if person.sells and person.role != ADMIN else {"percent": 0.0, "new_client": 0.0}
    return {"percent": person.commission_percent if person.commission_percent is not None else general["percent"],
            "new_client": (person.commission_new_client if person.commission_new_client is not None
                           else general["new_client"])}


def invoice_context(db: Session, invoice: Invoice) -> dict:
    """Project, opportunity, account and seller of an invoice."""
    project = db.get(Project, invoice.budget.project_id) if invoice.budget else None
    opportunity = db.get(Opportunity, project.opportunity_id) if project and project.opportunity_id else None
    account_id = (opportunity.account_id if opportunity else None) or (project.account_id if project else None)
    account = db.get(Account, account_id) if account_id else None
    owner_id = (opportunity.owner_id if opportunity and opportunity.owner_id else None) or \
        (account.owner_id if account else None)
    return {"project": project, "opportunity": opportunity, "account": account,
            "seller": db.get(User, owner_id) if owner_id else None}


def without_iva(invoice: Invoice) -> float:
    tax = (invoice.line.tax_percentage or 0.0) if invoice.line else 0.0
    return (invoice.amount or 0.0) / (1 + tax / 100)


def _new(db: Session, by: User, context: dict, invoice: Invoice, paid_on, kind: str, amount: float,
         description: str, **fields) -> Commission:
    seller, account, project = context["seller"], context["account"], context["project"]
    client = (account.name if account else None) or (project.client_display_name or project.name if project else "")
    adjustment = PayrollAdjustment(user_id=seller.id, kind="comision", amount=amount, created_by_id=by.id,
                                   description=f"{description} · {client}"[:200])
    db.add(adjustment)
    db.flush()
    commission = Commission(user_id=seller.id, kind=kind, invoice_id=invoice.id,
                            project_id=project.id if project else None,
                            opportunity_id=context["opportunity"].id if context["opportunity"] else None,
                            account_id=account.id if account else None, client_name=client,
                            invoice_number=invoice.invoice_number,
                            payment_date=paid_on,
                            amount=amount, adjustment_id=adjustment.id, **fields)
    db.add(commission)
    return commission


def create_for_paid_invoice(db: Session, invoice: Invoice, by: User, paid_on: date) -> List[Commission]:
    """Called when an invoice becomes PAGADA (paid_on: the date of the payment that completed it).
    Never twice for the same invoice or new client."""
    context = invoice_context(db, invoice)
    seller = context["seller"]
    if not seller:
        return []
    rules = rules_for(db, seller)
    created = []
    if rules["percent"] > 0 and not db.query(Commission).filter(
            Commission.kind == "factura", Commission.invoice_id == invoice.id).first():
        base = round(without_iva(invoice), 2)
        amount = round(base * rules["percent"] / 100, 2)
        if amount > 0:
            created.append(_new(db, by, context, invoice, paid_on, "factura", amount,
                                f"Comisión {rules['percent']:g}% factura #{invoice.invoice_number}",
                                base_amount=base, rate=rules["percent"]))
    opportunity = context["opportunity"]
    if rules["new_client"] > 0 and opportunity and opportunity.kind == "nuevo" and not db.query(Commission).filter(
            Commission.kind == "cliente_nuevo", Commission.opportunity_id == opportunity.id).first():
        created.append(_new(db, by, context, invoice, paid_on, "cliente_nuevo", round(rules["new_client"], 2),
                            f"Comisión cliente nuevo (factura #{invoice.invoice_number})"))
    return created


def status_of(commission: Commission) -> dict:
    """Where the commission is: waiting, in a draft payroll, paid (and in which payroll), cancelled."""
    period_id = None
    adjustment = commission.adjustment
    if adjustment and adjustment.lines:
        entry = adjustment.lines[0].entry
        period_id = entry.payroll_period_id
        state = "pagada" if entry.period.status == "final" else "borrador"
    else:
        state = "pendiente"
    if commission.cancelled_at:
        state = "revertida" if commission.reversal_adjustment_id else "anulada"
    return {"code": state, "label": STATUS_LABELS[state], "period_id": period_id}


def cancel(db: Session, commission: Commission, reason: str, by: User) -> str:
    """Cancel a commission. Waiting or in a draft: it disappears. Already paid in an approved
    payroll: a negative adjustment takes it back in the next payroll."""
    if commission.cancelled_at:
        raise ValueError("Esa comisión ya está anulada")
    state = status_of(commission)
    adjustment = commission.adjustment
    if state["code"] == "pagada":
        reversal = PayrollAdjustment(user_id=commission.user_id, kind="comision", amount=-commission.amount,
                                     source_period_id=state["period_id"], created_by_id=by.id,
                                     description=f"Reversión: {adjustment.description}"[:200])
        db.add(reversal)
        db.flush()
        commission.reversal_adjustment_id = reversal.id
        message = "Comisión revertida: se descuenta en la próxima planilla"
    else:
        if adjustment:
            for line in list(adjustment.lines):
                entry = line.entry
                entry.lines.remove(line)
                recompute(entry)
            commission.adjustment_id = None
            db.delete(adjustment)
        message = "Comisión anulada" + (" y quitada de la planilla en borrador" if state["code"] == "borrador" else "")
    commission.cancelled_at = datetime.now(timezone.utc)
    commission.cancel_reason = (reason or "").strip()[:255] or None
    commission.cancelled_by_id = by.id
    return message
