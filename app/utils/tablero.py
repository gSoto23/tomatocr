"""Import of the pilot's sales board ("Tablero comercial", exported as tablero.json) into
the CRM. docs/DISENO_CRM.md, section 6. Each lead becomes an opportunity with
origin_ref "tablero:<id>", so importing the same file twice adds nothing."""
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Dict, List, Optional

from sqlalchemy.orm import Session

from app.db.models.crm import LABELS, MOTORS, STAGES, Account, Contact, CrmActivity, Opportunity
from app.db.models.user import User
from app.utils.crm import guess_kind
from app.utils.leads import EMAIL_RE, find_account

MOTOR_MAP = {LABELS["motor"][m]: m for m in MOTORS}
STAGE_MAP = {"prospecto": "prospecto", "respuesta": "respuesta", "reunion": "reunion", "propuesta": "propuesta",
             "cerrado": "ganado", "perdido": "perdido"}
FALLBACK_OWNER = "Gerardo"


@dataclass
class ImportReport:
    rows: List[Dict] = field(default_factory=list)
    counts: Dict[str, int] = field(default_factory=dict)

    def add(self, action: str, lead: Dict, detail: str = ""):
        self.rows.append({"accion": action, "id": lead.get("id", ""), "empresa": lead.get("empresa", ""),
                          "detalle": detail})
        self.counts[action] = self.counts.get(action, 0) + 1


def plain(text: str) -> str:
    text = unicodedata.normalize("NFKD", text or "")
    return "".join(c for c in text if not unicodedata.combining(c)).strip().lower()


def parse_day(value: Optional[str]) -> Optional[date]:
    try:
        return date.fromisoformat((value or "").strip()[:10])
    except ValueError:
        return None


def split_contact_data(value: str) -> Dict[str, Optional[str]]:
    """The board has one free-text field for e-mail or phone."""
    value = (value or "").strip()
    email = re.search(r"[^@\s,;]+@[^@\s,;]+\.[^@\s,;]+", value)
    if email and EMAIL_RE.match(email.group(0)):
        return {"email": email.group(0).lower(), "phone": None, "other": None}
    if len(re.sub(r"\D", "", value)) >= 8:
        return {"email": None, "phone": value[:30], "other": None}
    return {"email": None, "phone": None, "other": value or None}


class OwnerFinder:
    """Board names (Melina, Albert, Gerardo, Alina) → active admin/ventas users."""

    def __init__(self, db: Session):
        self.db = db
        self.cache: Dict[str, Optional[User]] = {}

    def find(self, name: str) -> Optional[User]:
        key = plain(name)
        if key not in self.cache:
            users = [u for u in self.db.query(User).filter(User.role.in_(("admin", "ventas")),
                                                              User.is_active != False).all()  # noqa: E712
                     if key and plain(u.full_name or "").split(" ")[0] == key]
            self.cache[key] = users[0] if len(users) == 1 else None
        return self.cache[key]


def import_leads(db: Session, leads: List[Dict], user: Optional[User] = None) -> ImportReport:
    """Adds accounts, contacts, opportunities and notes for the leads not imported yet.
    Does not commit: the caller commits (--apply) or rolls back (dry run)."""
    report = ImportReport()
    owners = OwnerFinder(db)
    fallback = owners.find(FALLBACK_OWNER)
    for lead in leads:
        lead_id = str(lead.get("id") or "").strip()
        company = str(lead.get("empresa") or "").strip()
        motor = MOTOR_MAP.get(str(lead.get("motor") or "").strip())
        stage = STAGE_MAP.get(plain(lead.get("etapa")))
        problems = [text for ok, text in ((lead_id, "sin id"), (company, "sin empresa"), (motor, "motor desconocido"),
                                          (stage, "etapa desconocida")) if not ok]
        if problems:
            report.add("error", lead, ", ".join(problems))
            continue
        origin = f"tablero:{lead_id}"
        if db.query(Opportunity).filter(Opportunity.origin_ref == origin).first():
            report.add("omitido", lead, "ya importado")
            continue

        notes = []
        owner = owners.find(lead.get("responsable") or "")
        if owner is None:
            owner = fallback
            notes.append(f"Responsable en el tablero: {lead.get('responsable') or '—'}")
        source = plain(lead.get("fuente"))[:30] or "tablero"
        data = split_contact_data(lead.get("dato"))
        if data["other"]:
            notes.append(f"Dato de contacto: {data['other']}")
        created = parse_day(lead.get("creado"))
        updated = parse_day(lead.get("actualizado")) or created
        created_at = datetime.combine(created, datetime.min.time()) if created else datetime.utcnow()
        updated_at = datetime.combine(updated, datetime.min.time()) if updated else created_at

        account = find_account(db, {"email": data["email"] or "", "company": company})
        detail = []
        if account is None:
            account = Account(name=company[:200], kind=guess_kind(company), owner_id=owner.id if owner else None,
                              source=source, origin_ref=origin[:50], created_at=created_at,
                              created_by_id=user.id if user else None)
            db.add(account)
            db.flush()
            report.counts["cuentas nuevas"] = report.counts.get("cuentas nuevas", 0) + 1
            detail.append("cuenta nueva")
        else:
            detail.append(f"cuenta existente #{account.id} {account.name}")
            if db.query(Opportunity).filter(Opportunity.account_id == account.id, Opportunity.motor == motor,
                                            Opportunity.stage.notin_(("ganado", "perdido"))).first():
                detail.append("ya tenía una oportunidad abierta de ese motor")

        contact = None
        name = str(lead.get("contacto") or "").strip()
        if name or data["email"] or data["phone"]:
            contact = next((c for c in account.contacts if data["email"] and (c.email or "").lower() == data["email"]), None) \
                or next((c for c in account.contacts if data["phone"] and c.phone == data["phone"]), None) \
                or next((c for c in account.contacts if name and plain(c.name) == plain(name)), None)
            if contact is None:
                contact = Contact(account_id=account.id, name=(name or "Sin nombre")[:150],
                                  role_title=str(lead.get("cargo") or "").strip()[:100] or None,
                                  email=data["email"], phone=data["phone"], is_primary=not account.contacts,
                                  is_commercial=True, origin_ref=origin[:50], created_at=created_at)
                db.add(contact)
                db.flush()
                detail.append("contacto nuevo")

        reached = lead.get("alcanzo")
        reached = reached if isinstance(reached, int) and 0 <= reached <= 4 else 0
        max_stage = reached if stage == "perdido" else max(reached, STAGES.index(stage))
        opportunity = Opportunity(
            account_id=account.id, title=f"{LABELS['motor'][motor]} · tablero", motor=motor, stage=stage,
            max_stage=max_stage, owner_id=owner.id if owner else None, source=source, origin_ref=origin,
            next_step=str(lead.get("proximo") or "").strip()[:255] or None, next_step_date=parse_day(lead.get("fecha")),
            lost_reason="Registrado como perdido en el tablero" if stage == "perdido" else None,
            created_by_id=user.id if user else None, created_at=created_at, updated_at=updated_at,
        )
        db.add(opportunity)
        db.flush()
        if lead.get("notas"):
            notes.insert(0, str(lead["notas"]).strip())
        if notes:
            db.add(CrmActivity(account_id=account.id, opportunity_id=opportunity.id,
                               contact_id=contact.id if contact else None, type="nota", happened_at=updated_at,
                               notes="Del tablero comercial:\n" + "\n".join(notes), user_id=owner.id if owner else None))
        detail.append(f"{LABELS['stage'][stage]}, {owner.full_name if owner else 'sin responsable'}")
        report.add("importado", lead, "; ".join(detail))
    return report
