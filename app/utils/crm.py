"""CRM helpers: name matching, client backfill, duplicate detection and merge.
See docs/DISENO_CRM.md, sections 2 and 3."""
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from difflib import SequenceMatcher
from typing import Dict, List, Optional, Tuple

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.db.models.activity import ActivityLog
from app.db.models.crm import (DEFAULT_GOALS, FUNNEL_STAGES, LABELS, STAGES, Account, AccountNotDuplicate, Contact,
                                CrmActivity, CrmGoal, Opportunity, ProjectContactRole, stage_index)
from app.db.models.project_details import ProjectContact
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


def account_status(db: Session, account: Account) -> str:
    """cliente: an active project or a reforestation project; ex_cliente: only closed
    projects; prospecto: no projects yet; descartada: set by hand."""
    if account.discarded_at:
        return "descartada"
    if db.query(ReforestationProject.id).filter(ReforestationProject.account_id == account.id).first():
        return "cliente"
    projects = db.query(Project.is_active).filter(Project.account_id == account.id).all()
    if any(active is not False for (active,) in projects):
        return "cliente"
    return "ex_cliente" if projects else "prospecto"


# --- Backfill ------------------------------------------------------------------

@dataclass
class BackfillReport:
    rows: List[Dict[str, str]] = field(default_factory=list)
    counts: Dict[str, int] = field(default_factory=dict)
    new_accounts: List[Account] = field(default_factory=list)

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


def _new_account(db, matcher, report, name, origin, owner, tax_id=None):
    account = Account(name=name.strip(), kind=guess_kind(name), owner_id=owner.id if owner else None,
                      created_by_id=owner.id if owner else None, origin_ref=origin, source="migracion",
                      tax_id=tax_id if tax_id and tax_id not in matcher.by_tax else None)
    db.add(account)
    db.flush()
    matcher.remember(account)
    report.add("cuenta nueva", account, origin)
    report.new_accounts.append(account)
    return account


def _add_contact(db, report, account, origin, name=None, email=None, phone=None, user_id=None, role_title=None):
    """Adds a contact unless the account already has one with that email, phone or name."""
    name, email, phone = (name or "").strip(), (email or "").strip().lower() or None, (phone or "").strip() or None
    if not (name or email or phone):
        return None
    for c in account.contacts:
        if (email and c.email and c.email.lower() == email) or (phone and c.phone == phone) \
                or (name and normalize_name(c.name) == normalize_name(name)):
            if user_id and not c.user_id:
                c.user_id = user_id
            for attr, value in (("email", email), ("phone", phone), ("role_title", role_title)):
                if value and not getattr(c, attr):
                    setattr(c, attr, value)
            return c
    contact = Contact(account=account, name=name or email or phone, email=email, phone=phone, user_id=user_id,
                      role_title=(role_title or "").strip() or None, is_primary=not account.contacts, origin_ref=origin)
    db.add(contact)
    db.flush()
    report.add("contacto nuevo", account, origin, contact.name)
    return contact


def backfill(db: Session, owner: User, today: Optional[date] = None) -> BackfillReport:
    """Creates accounts and contacts from current clients, projects, quotes and reforestation.

    Idempotent: records already linked (project/quote/reforestation account_id, or a
    contact with the portal user) are skipped, and contacts are matched by email,
    phone or name, so running it twice adds nothing. Project contacts are copied to
    the account's single contact list and linked back to their project; run it again
    to pick up contacts added to projects later.
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
        account = matcher.find(name) or _new_account(db, matcher, report, name, f"user:{user.id}", owner)
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
                account = _new_account(db, matcher, report, name, origin, owner)
                how = "cuenta nueva"
        project.account_id = account.id
        report.add("proyecto ligado", account, origin, f"{project.name} ({how})")
    db.flush()

    # 2b. Project contacts (and the old single contact fields) -> the account's contact list,
    # linked back to the project as site contacts; those with email receive the reports.
    for project in db.query(Project).filter(Project.account_id.isnot(None)).order_by(Project.id):
        account = db.get(Account, project.account_id)
        people = [(pc.name, pc.email, pc.phone, pc.position, f"project_contact:{pc.id}")
                  for pc in db.query(ProjectContact).filter(ProjectContact.project_id == project.id).order_by(ProjectContact.id)]
        if not people and (project.contact_name or project.contact_email or project.contact_phone):
            people = [(project.contact_name, project.contact_email, project.contact_phone, None, f"project:{project.id}")]
        for name, email, phone, position, origin in people:
            contact = _add_contact(db, report, account, origin, name, email, phone, role_title=position)
            if contact is None:
                continue
            if not db.get(ProjectContactRole, (project.id, contact.id)):
                db.add(ProjectContactRole(project_id=project.id, contact_id=contact.id, is_site=True,
                                          receives_reports=bool(contact.email), position=(position or "").strip() or None))
                db.flush()
                report.add("contacto del proyecto", account, origin, f"{contact.name} en {project.name}")

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
            account = _new_account(db, matcher, report, name, origin, owner, tax_id=tax_id)
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
        account = matcher.find(name) or _new_account(db, matcher, report, name, origin, owner)
        reforestation.account_id = account.id
        report.add("reforestación ligada", account, origin, name)
    db.flush()

    # 5. Recent quotes of prospects become opportunities in "propuesta".
    since = today - timedelta(days=RECENT_QUOTE_DAYS)
    for quote in db.query(Quote).filter(Quote.opportunity_id.is_(None), Quote.fecha_emision >= since).order_by(Quote.id):
        account = db.get(Account, quote.account_id)
        if account is None or account_status(db, account) != "prospecto":
            continue
        # No amount_crc: while a quote is linked, the amount comes from the quote.
        opportunity = Opportunity(
            account_id=account.id, title=f"Cotización {quote.numero_cotizacion}", stage="propuesta",
            max_stage=stage_index("propuesta"), owner_id=account.owner_id, source="cotizador", created_by_id=owner.id,
        )
        db.add(opportunity)
        db.flush()
        quote.opportunity_id = opportunity.id
        report.add("oportunidad nueva", account, f"quote:{quote.id}", f"{quote.numero_cotizacion} del {quote.fecha_emision}")

    # Computed status of the new accounts, for the review.
    for account in report.new_accounts:
        report.add("estado calculado", account, "", account_status(db, account))

    # 6. Possible duplicates, for review only.
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


MERGE_FIELDS = ("legal_name", "tax_id", "source", "owner_id", "province", "address", "website",
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
    if keep.discarded_at and not drop.discarded_at:
        keep.discarded_at = None  # the merged account is still active
    if drop.notes:
        keep.notes = f"{keep.notes}\n{drop.notes}" if keep.notes else drop.notes
    drop.merged_into_id = keep.id
    db.add(ActivityLog(user_id=user.id, action="MERGE", entity_type="ACCOUNT", entity_id=keep.id,
                       details=f"Cuenta '{drop.name}' (#{drop.id}) fusionada en '{keep.name}' (#{keep.id}): "
                               + ", ".join(f"{v} {k}" for k, v in moved.items() if v)))
    db.commit()
    return moved


# --- Pipeline, permissions and follow-ups (sub-fase 2B) -----------------------------



CLOSED_STAGES = ("ganado", "perdido")


def can_edit_account(user: User, account: Account) -> bool:
    """Admin edits everything; ventas edits its own accounts and unowned ones."""
    if user.role == "admin":
        return True
    return user.role == "ventas" and account.owner_id in (None, user.id)


def can_edit_opportunity(user: User, opportunity: Opportunity) -> bool:
    if user.role == "admin":
        return True
    return user.role == "ventas" and opportunity.owner_id in (None, user.id)


def claim_if_unowned(entity, user: User):
    """A seller who edits an unowned account or opportunity becomes its owner."""
    if entity.owner_id is None and user.role == "ventas":
        entity.owner_id = user.id


def goals(db: Session) -> Dict[str, int]:
    stored = {g.stage: g.target for g in db.query(CrmGoal)}
    return {stage: stored.get(stage, DEFAULT_GOALS[stage]) for stage in FUNNEL_STAGES}


def set_goals(db: Session, targets: Dict[str, int]):
    for stage in FUNNEL_STAGES:
        if stage in targets:
            goal = db.get(CrmGoal, stage) or CrmGoal(stage=stage)
            goal.target = max(0, int(targets[stage]))
            db.add(goal)
    db.commit()


def quote_amount(db: Session, opportunity: Opportunity) -> Optional[float]:
    """Latest linked quote in colones; otherwise the amount typed in the opportunity."""
    quote = db.query(Quote).filter(Quote.opportunity_id == opportunity.id).order_by(
        Quote.fecha_emision.desc(), Quote.id.desc()).first()
    if quote is not None:
        return quote.total if (quote.moneda or "CRC").upper() == "CRC" else None
    return opportunity.amount_crc


def filter_opportunities(query, motor: Optional[str] = None, owner_id: Optional[int] = None,
                         stage: Optional[str] = None, search: Optional[str] = None):
    if motor:
        query = query.filter(Opportunity.motor == motor)
    if owner_id:
        query = query.filter(Opportunity.owner_id == owner_id)
    if stage:
        query = query.filter(Opportunity.stage == stage)
    if search:
        like = f"%{search.strip()}%"
        query = query.join(Account, Account.id == Opportunity.account_id).filter(
            (Opportunity.title.ilike(like)) | (Account.name.ilike(like)))
    return query


def funnel(db: Session, motor: Optional[str] = None, owner_id: Optional[int] = None) -> List[Dict]:
    """Accounts that reached each stage (by the highest stage of any of their opportunities)."""
    query = filter_opportunities(db.query(Opportunity.account_id, Opportunity.max_stage), motor, owner_id)
    best: Dict[int, int] = {}
    for account_id, max_stage in query:
        best[account_id] = max(best.get(account_id, 0), max_stage or 0)
    targets = goals(db)
    rows = []
    for index, stage in enumerate(FUNNEL_STAGES):
        reached = sum(1 for value in best.values() if value >= index)
        target = targets[stage]
        rows.append({"stage": stage, "reached": reached, "target": target,
                     "pct": round(100 * reached / target) if target else None})
    return rows


def proposal_amounts(db: Session, owner_id: Optional[int] = None) -> Dict[str, float]:
    """Amount in open proposals by motor, taken from the linked quotes."""
    query = db.query(Opportunity).filter(Opportunity.stage == "propuesta")
    if owner_id:
        query = query.filter(Opportunity.owner_id == owner_id)
    totals: Dict[str, float] = {}
    for opportunity in query:
        amount = quote_amount(db, opportunity)
        if amount:
            key = opportunity.motor or "sin_motor"
            totals[key] = totals.get(key, 0) + amount
    return totals


def next_steps(db: Session, owner_id: Optional[int] = None, today: Optional[date] = None) -> Dict[str, List[Opportunity]]:
    """Open opportunities with a next-step date: overdue, today and the next 7 days."""
    today = today or date.today()
    query = db.query(Opportunity).filter(Opportunity.stage.notin_(CLOSED_STAGES),
                                         Opportunity.next_step_date.isnot(None))
    if owner_id:
        query = query.filter(Opportunity.owner_id == owner_id)
    result = {"vencidos": [], "hoy": [], "semana": []}
    for opportunity in query.order_by(Opportunity.next_step_date, Opportunity.id):
        if opportunity.next_step_date < today:
            result["vencidos"].append(opportunity)
        elif opportunity.next_step_date == today:
            result["hoy"].append(opportunity)
        elif opportunity.next_step_date <= today + timedelta(days=7):
            result["semana"].append(opportunity)
    return result


def change_stage(db: Session, opportunity: Opportunity, stage: str, user: User, lost_reason: Optional[str] = None):
    """Moves an opportunity; records a follow-up and an audit entry. "perdido" keeps the highest stage reached."""
    if stage not in STAGES:
        raise ValueError("Etapa no válida")
    if stage == "perdido" and not (lost_reason or "").strip():
        raise ValueError("Indique por qué se perdió")
    if stage == opportunity.stage:
        return
    previous = opportunity.stage
    opportunity.stage = stage
    if stage != "perdido":
        opportunity.max_stage = max(opportunity.max_stage or 0, stage_index(stage))
        opportunity.lost_reason = None
    else:
        opportunity.lost_reason = lost_reason.strip()
    note = f"{LABELS['stage'][previous]} → {LABELS['stage'][stage]}"
    if stage == "perdido":
        note += f". Motivo: {opportunity.lost_reason}"
    db.add(CrmActivity(account_id=opportunity.account_id, opportunity_id=opportunity.id, type="cambio_etapa",
                       happened_at=datetime.utcnow(), notes=note, user_id=user.id))
    db.add(ActivityLog(user_id=user.id, action="UPDATE", entity_type="OPPORTUNITY", entity_id=opportunity.id,
                       details=f"{opportunity.title}: {note}"))


def similar_accounts(db: Session, name: str, tax_id: Optional[str] = None, email: Optional[str] = None) -> List[Account]:
    """Existing accounts that could be the same client: same cédula, contact email, or a similar name."""
    found = {}
    for account in active_accounts(db):
        if tax_id and account.tax_id and account.tax_id == tax_id.strip():
            found[account.id] = account
        elif name and (normalize_name(account.name) == normalize_name(name)
                       or similarity(account.name, name) >= SIMILARITY_THRESHOLD):
            found[account.id] = account
    if email:
        for contact in db.query(Contact).filter(Contact.email == email.strip().lower()):
            account = db.get(Account, contact.account_id)
            if account and not account.merged_into_id:
                found[account.id] = account
    return list(found.values())


def last_followups(db: Session) -> Dict[int, datetime]:
    return dict(db.query(CrmActivity.account_id, func.max(CrmActivity.happened_at)).group_by(CrmActivity.account_id))

