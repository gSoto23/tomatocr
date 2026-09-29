"""Lead intake from the tomatocr.com contact form and from darboles.com (server to
server). docs/DISENO_CRM.md, section 6."""
import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.db.models.activity import ActivityLog
from app.db.models.crm import (ASSIGNMENT_DEFAULT, LABELS, MOTORS, Account, Contact, CrmActivity, CrmAssignment,
                               LeadSubmission, Opportunity)
from app.db.models.user import User
from app.utils.crm import active_accounts, guess_kind, normalize_name
from app.utils.login_throttle import trackable_ip

# Bump when the consent text on the form or /privacidad changes; stored with each consent.
CONSENT_TEXT_VERSION = "2026-09-27"
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
SOURCES = {"web": "formulario web", "darboles": "darboles.com"}
LIMITS = {"name": 150, "company": 200, "email": 150, "phone": 30, "message": 3000}


class LeadRejected(ValueError):
    def __init__(self, errors: List[str]):
        super().__init__("; ".join(errors))
        self.errors = errors


@dataclass
class LeadResult:
    account: Account
    contact: Contact
    opportunity: Opportunity
    new_account: bool
    new_opportunity: bool


def clean_lead(data: Dict) -> Dict:
    """Validates the fields shared by the web form and the darboles.com API."""
    get = lambda key: str(data.get(key) or "").strip()
    lead = {key: get(key)[:limit] for key, limit in LIMITS.items()}
    lead["email"] = lead["email"].lower()
    lead["motor"] = get("motor")
    errors = []
    if not lead["name"]:
        errors.append("Escribí tu nombre")
    if not lead["email"] and not lead["phone"]:
        errors.append("Dejanos un correo o un teléfono")
    if lead["email"] and not EMAIL_RE.match(lead["email"]):
        errors.append("Revisá el correo, no parece válido")
    if lead["motor"] not in MOTORS:
        errors.append("Elegí qué te interesa")
    consent = data.get("consent")
    if not (consent is True or str(consent).lower() in ("true", "1", "on", "si", "sí")):
        errors.append("Aceptá la política de privacidad para que podamos contactarte")
    if errors:
        raise LeadRejected(errors)
    lead["consent_text_version"] = get("consent_text_version")[:20] or CONSENT_TEXT_VERSION
    return lead


def rate_limited(db: Session, source: str, ip: Optional[str], per_ip: int, per_hour: int) -> bool:
    """True when this IP (if it is a real client IP) or the whole source went over the hourly limit."""
    since = datetime.utcnow() - timedelta(hours=1)
    query = db.query(func.count(LeadSubmission.id)).filter(LeadSubmission.source == source,
                                                            LeadSubmission.created_at > since)
    if query.scalar() >= per_hour:
        return True
    ip = trackable_ip(ip)
    return bool(ip) and query.filter(LeadSubmission.ip_address == ip).scalar() >= per_ip


def record_submission(db: Session, source: str, ip: Optional[str]):
    db.add(LeadSubmission(source=source, ip_address=trackable_ip(ip)))
    db.commit()


def assigned_owner(db: Session, motor: str) -> Optional[User]:
    for key in (motor, ASSIGNMENT_DEFAULT):
        row = db.get(CrmAssignment, key)
        if row and row.user_id:
            user = db.get(User, row.user_id)
            if user and user.is_active is not False and user.role in ("admin", "ventas"):
                return user
    return db.query(User).filter(User.role == "admin", User.is_active != False).order_by(User.id).first()  # noqa: E712


def find_account(db: Session, lead: Dict) -> Optional[Account]:
    if lead["email"]:
        contact = db.query(Contact).filter(func.lower(Contact.email) == lead["email"]).first()
        if contact:
            account = db.get(Account, contact.account_id)
            while account is not None and account.merged_into_id:
                account = db.get(Account, account.merged_into_id)
            if account:
                return account
    if lead["company"]:
        key = normalize_name(lead["company"])
        return next((a for a in active_accounts(db) if normalize_name(a.name) == key), None)
    return None


def intake_lead(db: Session, lead: Dict, source: str) -> LeadResult:
    """Finds or creates the account and contact (never duplicating by email or company
    name), stores the consent, and opens an opportunity for the right seller. A second
    request for the same motor while an opportunity is open adds a note to it instead."""
    now = datetime.utcnow()
    account = find_account(db, lead)
    new_account = account is None
    if new_account:
        name = lead["company"] or lead["name"]
        owner = assigned_owner(db, lead["motor"])
        account = Account(name=name, kind=guess_kind(name) if lead["company"] else "persona",
                          owner_id=owner.id if owner else None, source=source, origin_ref=f"{source}:{now:%Y%m%d%H%M%S}")
        db.add(account)
        db.flush()
    elif account.discarded_at:
        # Someone discarded asks again: back to the tables with the new request.
        account.discarded_at = None
        account.discard_reason = None
        db.add(CrmActivity(account_id=account.id, type="nota", happened_at=now,
                           notes=f"Reactivada: llegó una solicitud nueva desde {SOURCES[source]}"))

    contact = None
    if lead["email"]:
        contact = next((c for c in account.contacts if (c.email or "").lower() == lead["email"]), None)
    if contact is None and lead["phone"]:
        contact = next((c for c in account.contacts if c.phone == lead["phone"]), None)
    if contact is None:
        contact = Contact(account_id=account.id, name=lead["name"], email=lead["email"] or None,
                          phone=lead["phone"] or None, is_primary=not account.contacts, is_commercial=True,
                          origin_ref=source)
        db.add(contact)
        db.flush()
    else:
        contact.phone = contact.phone or lead["phone"] or None
        contact.email = contact.email or lead["email"] or None
    contact.consent_marketing = True
    contact.consent_at = now
    contact.consent_text_version = lead["consent_text_version"]

    opportunity = db.query(Opportunity).filter(
        Opportunity.account_id == account.id, Opportunity.motor == lead["motor"],
        Opportunity.stage.notin_(("ganado", "perdido"))).first()
    new_opportunity = opportunity is None
    if new_opportunity:
        # An existing client keeps its owner; a new one goes to the seller of that motor.
        owner = db.get(User, account.owner_id) if account.owner_id else assigned_owner(db, lead["motor"])
        owner_id = owner.id if owner else None
        opportunity = Opportunity(
            account_id=account.id, title=f"{LABELS['motor'][lead['motor']]} · {SOURCES[source]}",
            motor=lead["motor"], stage="prospecto", max_stage=0, owner_id=owner_id, source=source, origin="web",
            next_step="Responder la solicitud", next_step_date=date.today(),
        )
        db.add(opportunity)
        db.flush()

    note = f"Solicitud desde {SOURCES[source]}"
    if lead["message"]:
        note += f":\n{lead['message']}"
    db.add(CrmActivity(account_id=account.id, opportunity_id=opportunity.id, contact_id=contact.id, type="nota",
                       happened_at=now, notes=note))
    db.add(ActivityLog(action="CREATE", entity_type="LEAD", entity_id=opportunity.id,
                       details=f"Oportunidad {SOURCES[source]}: {account.name} ({LABELS['motor'][lead['motor']]})"))
    db.commit()
    return LeadResult(account, contact, opportunity, new_account, new_opportunity)


def notification(result: LeadResult, lead: Dict, source: str) -> Dict:
    """Subject and body of the internal e-mail about a new lead."""
    motor = LABELS["motor"][lead["motor"]]
    lines = [
        f"Nueva oportunidad desde {SOURCES[source]}.",
        "",
        f"Cuenta: {result.account.name}{' (nueva)' if result.new_account else ''}",
        f"Contacto: {lead['name']}",
        f"Correo: {lead['email'] or '—'}",
        f"Teléfono: {lead['phone'] or '—'}",
        f"Interés: {motor}",
        "",
        lead["message"] or "(sin mensaje)",
        "",
        f"Ver en el sistema: https://tomatocr.com/clientes/oportunidades/{result.opportunity.id}",
    ]
    return {"subject": f"Nueva oportunidad: {result.account.name} ({motor})", "body": "\n".join(lines)}
