"""Sellers' commissions (docs/PLAN_PLANILLA_CALENDARIO.md, Fase 5).

- When an invoice becomes PAGADA, its seller earns a % of its amount without IVA. With a threshold,
  an invoice under it earns one % and one at or above it another (on the whole invoice).
- When the first invoice of a "Nuevo" opportunity is paid, the seller earns the new-client amount.
- The seller is the project's vendedor encargado (by default the owner of the opportunity that
  made the project, or of the account); see app/utils/vendedor.py.
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
from app.utils.vendedor import project_seller

GENERAL_KEYS = {"percent": "commission_percent", "new_client": "commission_new_client",
                "threshold": "commission_threshold", "percent_high": "commission_percent_high"}
# A person's own rules, field by field (None: the general one).
OWN_FIELDS = {"percent": "commission_percent", "new_client": "commission_new_client",
              "threshold": "commission_threshold", "percent_high": "commission_percent_high"}
NO_RULES = {"percent": 0.0, "new_client": 0.0, "threshold": 0.0, "percent_high": 0.0}
KINDS = {"factura": "Factura cobrada", "cliente_nuevo": "Cliente nuevo"}
STATUS_LABELS = {"pendiente": "Para la planilla de fin de mes", "borrador": "En planilla (borrador)",
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


def set_general_rules(db: Session, percent: float, new_client: float, threshold: float = 0.0,
                      percent_high: float = 0.0) -> None:
    for name, value in (("percent", percent), ("new_client", new_client), ("threshold", threshold),
                        ("percent_high", percent_high)):
        key = GENERAL_KEYS[name]
        row = db.get(CrmSetting, key) or CrmSetting(key=key)
        row.value = str(max(0.0, value or 0.0))
        db.add(row)


def has_own_rules(person: User) -> bool:
    return any(getattr(person, field) is not None for field in OWN_FIELDS.values())


def rules_for(db: Session, person: Optional[User]) -> dict:
    """The person's own rules, otherwise the general ones (only for people who sell: ventas and
    supervisors marked "También vende"; an admin earns only with their own). Tiers go together:
    an own threshold uses the person's tiers (an empty % takes the general one); an own % without
    an own threshold is one % for every invoice."""
    if not person:
        return dict(NO_RULES)
    general = general_rules(db) if person.sells and person.role != ADMIN else dict(NO_RULES)
    own = {name: getattr(person, field) for name, field in OWN_FIELDS.items()}
    pick = lambda name: own[name] if own[name] is not None else general[name]  # noqa: E731
    rules = {"new_client": pick("new_client")}
    if own["threshold"] is not None:
        rules.update(threshold=own["threshold"], percent=pick("percent"), percent_high=pick("percent_high"))
    elif own["percent"] is not None:
        rules.update(threshold=0.0, percent=own["percent"], percent_high=own["percent"])
    else:
        rules.update(threshold=general["threshold"], percent=general["percent"], percent_high=general["percent_high"])
    return rules


def percent_for(rules: dict, base: float) -> float:
    """The % for an invoice of `base` (without IVA): with a threshold, the whole invoice takes the
    % of its tier (under it, or at and above it)."""
    if rules.get("threshold") and base >= rules["threshold"]:
        return rules.get("percent_high") or 0.0
    return rules.get("percent") or 0.0


def invoice_context(db: Session, invoice: Invoice) -> dict:
    """Project, opportunity, account and seller of an invoice."""
    project = db.get(Project, invoice.budget.project_id) if invoice.budget else None
    opportunity = db.get(Opportunity, project.opportunity_id) if project and project.opportunity_id else None
    account_id = (opportunity.account_id if opportunity else None) or (project.account_id if project else None)
    account = db.get(Account, account_id) if account_id else None
    # The project's vendedor encargado (by default the opportunity's or the account's owner).
    return {"project": project, "opportunity": opportunity, "account": account,
            "seller": project_seller(db, project) if project else
            (db.get(User, account.owner_id) if account and account.owner_id else None)}


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
    if not db.query(Commission).filter(Commission.kind == "factura", Commission.invoice_id == invoice.id).first():
        base = round(without_iva(invoice), 2)
        percent = percent_for(rules, base)
        amount = round(base * percent / 100, 2)
        if amount > 0:
            created.append(_new(db, by, context, invoice, paid_on, "factura", amount,
                                f"Comisión {percent:g}% factura #{invoice.invoice_number}",
                                base_amount=base, rate=percent))
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
        message = "Comisión revertida: se descuenta en la planilla de fin de mes"
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
