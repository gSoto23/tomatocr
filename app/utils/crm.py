"""CRM helpers: name matching, client backfill, duplicate detection and merge.
See docs/DISENO_CRM.md, sections 2 and 3."""
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date, timedelta
from difflib import SequenceMatcher
from typing import Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from app.db.models.activity import ActivityLog
from app.db.models.crm import Account, AccountNotDuplicate, Contact, CrmActivity, Opportunity, stage_index
from app.db.models.project import Project
from app.db.models.quote import Quote
from app.db.models.reforestation import ReforestationProject
from app.db.models.user import User

SIMILARITY_THRESHOLD = 0.85
RECENT_QUOTE_DAYS = 90
LEGAL_SUFFIXES = (
    "sociedad de responsabilidad limitada", "sociedad anonima", "limitada", "ltda", "srl", "sa",
)
PUBLIC_WORDS = ("municipalidad", "ministerio", "instituto", "museo", "universidad", "consejo", "junta",
                "asociacion de desarrollo", "caja costarricense", "poder judicial", "gobierno")
# Costa Rican IDs: 3-101-123456, 1-1234-5678, or 9-12 digits.
TAX_ID_RE = re.compile(r"^\d{1,2}-?\d{3,4}-?\d{3,6}$")


def normalize_name(name: Optional[str]) -> str:
    """'Tical S.A.' -> 'tical'; 'Municipalidad de Alajuela' -> 'municipalidad de alajuela'."""
    text = unicodedata.normalize("NFKD", name or "").encode("ascii", "ignore").decode("ascii").lower()
    text = re.sub(r"[^a-z0-9 ]+", " ", text.replace(".", ""))
    text = re.sub(r"\s+", " ", text).strip()
    for suffix in LEGAL_SUFFIXES:
        if text.endswith(" " + suffix):
            text = text[: -len(suffix) - 1].strip()
    return text


def similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, normalize_name(a), normalize_name(b)).ratio()


def looks_like_tax_id(value: Optional[str]) -> bool:
    return bool(value) and bool(TAX_ID_RE.match(value.strip().replace(" ", "")))


def guess_kind(name: str) -> str:
    normalized = normalize_name(name)
    return "institucion_publica" if any(normalized.startswith(w) or f" {w}" in normalized for w in PUBLIC_WORDS) else "otro"


def active_accounts(db: Session) -> List[Account]:
    return db.query(Account).filter(Account.merged_into_id.is_(None)).order_by(Account.id).all()


# --- Backfill ------------------------------------------------------------------

@dataclass
class BackfillReport:
    rows: List[Dict[str, str]] = field(default_factory=list)
    counts: Dict[str, int] = field(default_factory=dict)

    def add(self, action: str, account: Optional[Account], origin: str, detail: str = ""):
        self.rows.append({"accion": action, "cuenta": account.name if account else "",
                          "cuenta_id": str(account.id) if account and account.id else "",
                          "origen": origin, "detalle": detail})
        self.counts[action] = self.counts.get(action, 0) + 1


class _Matcher:
    """Finds existing accounts by tax id or normalized name, including those created in this run."""
    def __init__(self, db: Session):
        self.by_name: Dict[str, Account] = {}
        self.by_tax: Dict[str, Account] = {}
        for account in active_accounts(db):
            self.remember(account)

    def remember(self, account: Account):
        self.by_name.setdefault(normalize_name(account.name), account)
        if account.tax_id:
            self.by_tax.setdefault(account.tax_id, account)

    def find(self, name: Optional[str] = None, tax_id: Optional[str] = None) -> Optional[Account]:
        if tax_id and tax_id in self.by_tax:
            return self.by_tax[tax_id]
        key = normalize_name(name)
        return self.by_name.get(key) if key else None


def _new_account(db, matcher, report, name, origin, owner, status, tax_id=None):
    account = Account(name=name.strip(), status=status, kind=guess_kind(name), owner_id=owner.id if owner else None,
                      created_by_id=owner.id if owner else None, origin_ref=origin, source="migracion",
                      tax_id=tax_id if tax_id and tax_id not in matcher.by_tax else None)
    db.add(account)
    db.flush()
    matcher.remember(account)
    report.add("cuenta nueva", account, origin, f"estado {status}")
    return account


def _add_contact(db, report, account, origin, name=None, email=None, phone=None, user_id=None):
    """Adds a contact unless the account already has one with that email, phone or name."""
    name, email, phone = (name or "").strip(), (email or "").strip().lower() or None, (phone or "").strip() or None
    if not (name or email or phone):
        return None
    for c in account.contacts:
        if (email and c.email and c.email.lower() == email) or (phone and c.phone == phone) \
                or (name and normalize_name(c.name) == normalize_name(name)):
            if user_id and not c.user_id:
                c.user_id = user_id
            return c
    contact = Contact(account=account, name=name or email or phone, email=email, phone=phone, user_id=user_id,
                      is_primary=not account.contacts, origin_ref=origin)
    db.add(contact)
    db.flush()
    report.add("contacto nuevo", account, origin, contact.name)
    return contact


def backfill(db: Session, owner: User, today: Optional[date] = None) -> BackfillReport:
    """Creates accounts and contacts from current clients, projects, quotes and reforestation.

    Idempotent: records already linked (project/quote/reforestation account_id, or a
    contact with the portal user) are skipped, so running it twice adds nothing.
    Doesn't commit: the caller commits (--apply) or rolls back (dry run).
    """
    today = today or date.today()
    report = BackfillReport()
    matcher = _Matcher(db)
    linked_users = {c.user_id: c.account for c in db.query(Contact).filter(Contact.user_id.isnot(None))}

    # 1. Portal users with role client.
    for user in db.query(User).filter(User.role == "client").order_by(User.id):
        if user.id in linked_users:
            continue
        name = user.full_name or user.username
        account = matcher.find(name) or _new_account(db, matcher, report, name, f"user:{user.id}", owner, "cliente")
        _add_contact(db, report, account, f"user:{user.id}", name=name, email=user.email, phone=user.phone,
                     user_id=user.id)
        linked_users[user.id] = account

    # 2. Projects: by the assigned client user, then by client name.
    for project in db.query(Project).filter(Project.account_id.is_(None)).order_by(Project.id):
        origin = f"project:{project.id}"
        account = next((linked_users[u.id] for u in project.users if u.role == "client" and u.id in linked_users), None)
        how = "por usuario cliente asignado"
        if account is None:
            name = project.client_display_name or project.name
            account = matcher.find(name)
            how = "por nombre"
            if account is None:
                account = _new_account(db, matcher, report, name, origin, owner, "cliente")
                how = "cuenta nueva"
        project.account_id = account.id
        report.add("proyecto ligado", account, origin, f"{project.name} ({how})")
        _add_contact(db, report, account, origin, project.contact_name, project.contact_email, project.contact_phone)

    # 3. Quotes: by cédula when the field holds one, then by name.
    for quote in db.query(Quote).filter(Quote.account_id.is_(None)).order_by(Quote.id):
        origin = f"quote:{quote.id}"
        data = quote.cliente_datos or {}
        # The quote tool labels "id" as the contact's name; use it as a cédula only if it looks like one.
        raw_id = (data.get("id") or "").strip()
        tax_id = raw_id.replace(" ", "") if looks_like_tax_id(raw_id) else None
        contact_name = None if tax_id else raw_id
        name = quote.cliente_nombre or data.get("name") or f"Cotización {quote.numero_cotizacion}"
        account = matcher.find(name, tax_id)
        if account is None:
            account = _new_account(db, matcher, report, name, origin, owner, "prospecto", tax_id=tax_id)
        elif tax_id and not account.tax_id and tax_id not in matcher.by_tax:
            account.tax_id = tax_id
            matcher.remember(account)
        quote.account_id = account.id
        report.add("cotización ligada", account, origin, quote.numero_cotizacion)
        _add_contact(db, report, account, origin, contact_name or None, data.get("email"), data.get("phone"))

    # 4. Reforestation projects by name.
    for reforestation in db.query(ReforestationProject).filter(ReforestationProject.account_id.is_(None)):
        origin = f"reforestation:{reforestation.id}"
        name = reforestation.client_name or f"Reforestación {reforestation.id}"
        account = matcher.find(name) or _new_account(db, matcher, report, name, origin, owner, "cliente")
        reforestation.account_id = account.id
        report.add("reforestación ligada", account, origin, name)
    db.flush()

    # 5. Status: cliente with at least one project or reforestation; prospecto otherwise.
    for account in active_accounts(db):
        has_work = db.query(Project.id).filter(Project.account_id == account.id).first() or \
            db.query(ReforestationProject.id).filter(ReforestationProject.account_id == account.id).first()
        wanted = "cliente" if has_work else "prospecto"
        if account.status != "inactivo" and account.status != wanted:
            report.add("estado", account, f"account:{account.id}", f"{account.status} -> {wanted}")
            account.status = wanted

    # 6. Recent quotes of prospects become opportunities in "propuesta".
    since = today - timedelta(days=RECENT_QUOTE_DAYS)
    for quote in db.query(Quote).filter(Quote.opportunity_id.is_(None), Quote.fecha_emision >= since).order_by(Quote.id):
        account = db.get(Account, quote.account_id)
        if account is None or account.status != "prospecto":
            continue
        crc = (quote.moneda or "CRC").upper() == "CRC"
        opportunity = Opportunity(
            account_id=account.id, title=f"Cotización {quote.numero_cotizacion}", stage="propuesta",
            max_stage=stage_index("propuesta"), amount_crc=quote.total if crc else None, owner_id=account.owner_id,
            source="cotizador", created_by_id=owner.id,
        )
        db.add(opportunity)
        db.flush()
        quote.opportunity_id = opportunity.id
        detail = f"{quote.numero_cotizacion} del {quote.fecha_emision}"
        if not crc:
            detail += f" (monto en {quote.moneda}, no se copia a colones)"
        report.add("oportunidad nueva", account, f"quote:{quote.id}", detail)

    # 7. Possible duplicates, for review only.
    for a, b, score in find_duplicates(db):
        report.add("posible duplicado", a, f"account:{b.id}", f"{b.name} (similitud {score:.2f})")
    db.flush()
    return report


# --- Duplicates and merge -----------------------------------------------------------

def find_duplicates(db: Session) -> List[Tuple[Account, Account, float]]:
    """Pairs of active accounts with similar names or a shared contact email, minus dismissed pairs."""
    accounts = active_accounts(db)
    dismissed = {(d.account_a_id, d.account_b_id) for d in db.query(AccountNotDuplicate)}
    emails: Dict[int, set] = {}
    for contact in db.query(Contact).filter(Contact.email.isnot(None)):
        emails.setdefault(contact.account_id, set()).add(contact.email.lower())
    pairs = []
    for i, a in enumerate(accounts):
        for b in accounts[i + 1:]:
            if (a.id, b.id) in dismissed:
                continue
            score = similarity(a.name, b.name)
            if score >= SIMILARITY_THRESHOLD or (emails.get(a.id, set()) & emails.get(b.id, set())):
                pairs.append((a, b, score))
    return pairs


def dismiss_duplicate(db: Session, a_id: int, b_id: int, user: User):
    low, high = sorted((a_id, b_id))
    if not db.query(AccountNotDuplicate).filter_by(account_a_id=low, account_b_id=high).first():
        db.add(AccountNotDuplicate(account_a_id=low, account_b_id=high, user_id=user.id))


MERGE_FIELDS = ("legal_name", "tax_id", "segment", "source", "owner_id", "province", "address", "website",
                "vat_exemption_code")


def merge_accounts(db: Session, keep: Account, drop: Account, user: User) -> Dict[str, int]:
    """Moves everything from `drop` into `keep`, fills keep's empty fields, and marks drop as merged."""
    if keep.id == drop.id or drop.merged_into_id or keep.merged_into_id:
        raise ValueError("Esas cuentas no se pueden fusionar")
    moved = {
        "contactos": db.query(Contact).filter(Contact.account_id == drop.id).update({"account_id": keep.id}),
        "oportunidades": db.query(Opportunity).filter(Opportunity.account_id == drop.id).update({"account_id": keep.id}),
        "actividades": db.query(CrmActivity).filter(CrmActivity.account_id == drop.id).update({"account_id": keep.id}),
        "proyectos": db.query(Project).filter(Project.account_id == drop.id).update({"account_id": keep.id}),
        "cotizaciones": db.query(Quote).filter(Quote.account_id == drop.id).update({"account_id": keep.id}),
        "reforestación": db.query(ReforestationProject).filter(
            ReforestationProject.account_id == drop.id).update({"account_id": keep.id}),
    }
    tax_id = drop.tax_id
    drop.tax_id = None  # free the unique value before copying it
    db.flush()
    for attr in MERGE_FIELDS:
        if getattr(keep, attr) in (None, ""):
            setattr(keep, attr, tax_id if attr == "tax_id" else getattr(drop, attr))
    if keep.status == "prospecto" and drop.status == "cliente":
        keep.status = "cliente"
    if drop.notes:
        keep.notes = f"{keep.notes}\n{drop.notes}" if keep.notes else drop.notes
    drop.merged_into_id = keep.id
    drop.status = "inactivo"
    db.add(ActivityLog(user_id=user.id, action="MERGE", entity_type="ACCOUNT", entity_id=keep.id,
                       details=f"Cuenta '{drop.name}' (#{drop.id}) fusionada en '{keep.name}' (#{keep.id}): "
                               + ", ".join(f"{v} {k}" for k, v in moved.items() if v)))
    db.commit()
    return moved
