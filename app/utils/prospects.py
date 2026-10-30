"""Posibles clientes (app/db/models/prospect.py): checking a prospect, finding repeats among the
accounts and the other prospects, the order of the list, attempts, and turning one into an
account + opportunity in "Nueva" (only then it counts in the Filtro and the goals)."""
import re
import unicodedata
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional

from sqlalchemy.orm import Session

from app.core.roles import ADMIN
from app.db.models.crm import (ACCOUNT_KINDS, LABELS, MOTORS, Account, Contact, CrmActivity, Opportunity)
from app.db.models.activity import ActivityLog
from app.db.models.prospect import CHANNELS, OPEN_STATUSES, PROVINCES, SOURCES, Prospect, ProspectAttempt
from app.db.models.user import User
from app.utils.crm import SIMILARITY_THRESHOLD, account_status, claim_if_unowned, normalize_name, similar_accounts, similarity
from app.utils.leads import EMAIL_RE
from app.utils.quote_pdf import business_days_after
from app.utils.spam import phone_problem
from app.utils.timecr import CR_OFFSET, today_cr

PER_PAGE = 20
# A converted attempt keeps its channel in the account's follow-ups ("otro" becomes a note).
ACTIVITY_OF_CHANNEL = {"llamada": "llamada", "whatsapp": "whatsapp", "correo": "correo", "visita": "visita", "otro": "nota"}


def plain(text: Optional[str]) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", (text or "").lower()) if not unicodedata.combining(c))


def digits(phone: Optional[str]) -> str:
    only = re.sub(r"\D", "", phone or "")
    return only[3:] if len(only) == 11 and only.startswith("506") else only


def clean(value: Optional[str], size: int) -> Optional[str]:
    value = " ".join((value or "").split())
    return value[:size] or None


def can_edit(user: User, prospect: Prospect) -> bool:
    """Its seller and the admin; one without seller, any seller (who then keeps it)."""
    return user.role == ADMIN or prospect.owner_id in (None, user.id)


def parse_fields(form: Dict) -> Dict:
    """The prospect's fields from the form, checked. Raises ValueError with a message."""
    company = clean(form.get("company"), 200)
    if not company:
        raise ValueError("Escribí el nombre de la empresa o institución")
    phone, email = clean(form.get("phone"), 30), clean(form.get("email"), 150)
    if phone and phone_problem(phone):
        raise ValueError(phone_problem(phone))
    if email and not EMAIL_RE.match(email):
        raise ValueError("Revisá el correo")
    try:
        next_date = date.fromisoformat(form["next_contact_date"]) if form.get("next_contact_date") else None
    except ValueError:
        raise ValueError("Revisá la fecha del próximo intento")
    return {"company": company, "contact_name": clean(form.get("contact_name"), 150),
            "contact_role": clean(form.get("contact_role"), 100), "phone": phone,
            "email": email.lower() if email else None,
            "kind": form.get("kind") if form.get("kind") in ACCOUNT_KINDS else "empresa",
            "motor": form.get("motor") if form.get("motor") in MOTORS else None,
            "province": form.get("province") if form.get("province") in PROVINCES else None,
            "source": form.get("source") if form.get("source") in SOURCES else None,
            "notes": (form.get("notes") or "").strip() or None, "next_contact_date": next_date}


def similar_prospects(db: Session, company: str, phone: Optional[str], email: Optional[str],
                      exclude_id: Optional[int] = None) -> List[Prospect]:
    """Other prospects that look like the same company: similar name, same phone or e-mail."""
    found = []
    for p in db.query(Prospect).filter(Prospect.id != (exclude_id or 0)):
        same_name = normalize_name(p.company) == normalize_name(company) or similarity(p.company, company) >= SIMILARITY_THRESHOLD
        same_phone = bool(phone) and digits(p.phone) == digits(phone) and len(digits(phone)) >= 8
        same_email = bool(email) and (p.email or "") == email
        if same_name or same_phone or same_email:
            found.append(p)
    return found


def repeats(db: Session, fields: Dict, exclude_id: Optional[int] = None) -> Dict[str, list]:
    return {"accounts": similar_accounts(db, fields["company"], None, fields.get("email")),
            "prospects": similar_prospects(db, fields["company"], fields.get("phone"), fields.get("email"), exclude_id)}


# --- The list ---------------------------------------------------------------------

VIEWS = {"abiertos": "Por trabajar", "hoy": "Para hoy y atrasados", "convertido": "Convertidos",
         "descartado": "No le interesa", "todos": "Todos"}


def due(p: Prospect, today: date) -> bool:
    return p.is_open and p.next_contact_date is not None and p.next_contact_date <= today


def order_key(p: Prospect, today: date):
    """Overdue and today first (oldest date first), then the ones never called (newest first),
    then the rest by their next date."""
    if due(p, today):
        return (0, p.next_contact_date.toordinal(), 0)
    if p.status == "por_contactar" and p.next_contact_date is None:
        return (1, 0, -p.id)
    return (2, (p.next_contact_date or date.max).toordinal(), -p.id)


def search_text(p: Prospect) -> str:
    return plain(" ".join(filter(None, [p.company, p.contact_name, p.contact_role, p.email, p.phone, digits(p.phone),
                                        p.notes, p.province, (p.owner.full_name or p.owner.username) if p.owner else ""])))


def listing(db: Session, today: date, view: str = "abiertos", owner_id: Optional[int] = None, q: str = "",
            motor: str = "", province: str = "") -> List[Prospect]:
    rows = db.query(Prospect).all()
    if view in ("abiertos", "hoy"):
        rows = [p for p in rows if p.is_open]
    elif view in ("convertido", "descartado"):
        rows = [p for p in rows if p.status == view]
    if view == "hoy":
        rows = [p for p in rows if due(p, today)]
    if owner_id:
        rows = [p for p in rows if p.owner_id == owner_id]
    if motor in MOTORS:
        rows = [p for p in rows if p.motor == motor]
    if province in PROVINCES:
        rows = [p for p in rows if p.province == province]
    words = plain(q).split()
    if words:
        rows = [p for p in rows if all(w in search_text(p) for w in words)]
    if view in ("convertido", "descartado"):
        return sorted(rows, key=lambda p: p.updated_at or datetime.min, reverse=True)
    return sorted(rows, key=lambda p: order_key(p, today))


def due_count(db: Session, owner_id: int, today: date) -> int:
    return db.query(Prospect).filter(Prospect.owner_id == owner_id, Prospect.status.in_(OPEN_STATUSES),
                                     Prospect.next_contact_date <= today).count()


def week_summary(db: Session, today: date, owner_id: Optional[int] = None) -> Dict[str, int]:
    """Since Monday (Costa Rica): prospects contacted and converted. Informative, not a goal."""
    monday = datetime.combine(today - timedelta(days=today.weekday()), datetime.min.time()) + CR_OFFSET
    attempts = db.query(ProspectAttempt.prospect_id).filter(ProspectAttempt.happened_at >= monday)
    converted = db.query(Prospect).filter(Prospect.converted_at >= monday)
    if owner_id:
        attempts = attempts.join(Prospect).filter(Prospect.owner_id == owner_id)
        converted = converted.filter(Prospect.owner_id == owner_id)
    return {"contacted": attempts.distinct().count(), "converted": converted.count()}


# --- Working one ------------------------------------------------------------------

def add_attempt(prospect: Prospect, user: User, channel: str, notes: Optional[str], next_date: Optional[date]):
    now = datetime.utcnow()
    prospect.attempts.append(ProspectAttempt(user_id=user.id, channel=channel if channel in CHANNELS else "otro",
                                             notes=(notes or "").strip() or None, happened_at=now))
    prospect.last_contact_at = now
    prospect.next_contact_date = next_date
    if prospect.status == "por_contactar":
        prospect.status = "en_seguimiento"
    if prospect.owner_id is None:
        prospect.owner_id = user.id


def convert(db: Session, prospect: Prospect, user: User, account: Optional[Account] = None) -> Opportunity:
    """Turns the prospect into an opportunity in "Nueva" (origin Prospección) on a new account,
    or on `account` when it already existed. Its attempts and notes go to the account's history."""
    seller_id = prospect.owner_id or user.id
    if account is None:
        account = Account(name=prospect.company, kind=prospect.kind, province=prospect.province, owner_id=seller_id,
                          created_by_id=user.id, source="prospeccion")
        db.add(account)
        db.flush()
    else:
        claim_if_unowned(account, user)
    if prospect.contact_name or prospect.phone or prospect.email:
        known = [c for c in account.contacts if prospect.email and c.email == prospect.email]
        if not known:
            db.add(Contact(account_id=account.id, name=prospect.contact_name or prospect.email or prospect.phone,
                           role_title=prospect.contact_role, email=prospect.email, phone=prospect.phone,
                           is_primary=not account.contacts, is_commercial=True))
    status = account_status(db, account)
    motor = LABELS["motor"].get(prospect.motor)
    opportunity = Opportunity(
        account_id=account.id, title=(f"{motor} · {prospect.company}" if motor else prospect.company)[:200],
        kind="ampliacion" if status in ("cliente", "ex_cliente") else "nuevo", motor=prospect.motor,
        stage="prospecto", max_stage=0, owner_id=seller_id, created_by_id=user.id, source="prospeccion",
        origin="prospeccion", next_step="Dar seguimiento al primer contacto",
        next_step_date=prospect.next_contact_date if prospect.next_contact_date and prospect.next_contact_date >= today_cr()
        else business_days_after(today_cr(), 3),
    )
    db.add(opportunity)
    db.flush()
    for attempt in reversed(prospect.attempts):  # oldest first
        db.add(CrmActivity(account_id=account.id, opportunity_id=opportunity.id, user_id=attempt.user_id,
                           type=ACTIVITY_OF_CHANNEL.get(attempt.channel, "nota"), happened_at=attempt.happened_at,
                           notes=f"(Prospección) {attempt.notes or CHANNELS.get(attempt.channel, '')}"))
    summary = "Viene de Posibles clientes"
    if prospect.source:
        summary += f" (fuente: {SOURCES[prospect.source]})"
    db.add(CrmActivity(account_id=account.id, opportunity_id=opportunity.id, user_id=user.id, type="nota",
                       happened_at=datetime.utcnow(), notes=f"{summary}." + (f"\n{prospect.notes}" if prospect.notes else "")))
    prospect.status, prospect.converted_at = "convertido", datetime.utcnow()
    prospect.account_id, prospect.opportunity_id = account.id, opportunity.id
    db.add(ActivityLog(user_id=user.id, action="CREATE", entity_type="OPPORTUNITY", entity_id=opportunity.id,
                       details=f"{opportunity.title} ({account.name}), desde Posibles clientes"))
    return opportunity
