"""Clientes (CRM): funnel, accounts, account file, opportunities and follow-ups.
docs/DISENO_CRM.md and docs/ANALISIS_ENCAJE_CRM.md."""
from datetime import date, datetime
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Body, Depends, Form, HTTPException, Request, status
from fastapi.responses import JSONResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.core.roles import ADMIN, SUPERVISOR, VENTAS
from app.core.templates import templates
from app.db.models.crm import (ACCOUNT_KINDS, ACTIVITY_TYPES, ASSIGNMENT_DEFAULT, FUNNEL_STAGES, GOAL_STAGES, LABELS, MONEY_GOALS,
                               MOTORS, ORIGINS,
                               OPPORTUNITY_KINDS, STAGES, Account, Contact, CrmActivity, CrmAssignment, Opportunity,
                               ProjectContactRole)
from app.db.models.project import Project
from app.db.models.quote import Quote
from app.db.models.reforestation import ReforestationProject
from app.db.models.user import User
from app.routers import deps
from app.utils.activity import log_activity
from app.utils.email import send_plain_email
from app.utils.crm import (account_payload, account_status, active_accounts, anonymize_contact, can_edit_account,
                           can_edit_opportunity, delete_account, delete_blockers, discard_account, reactivate_account,
                           change_stage, claim_if_unowned, create_renewal, dismiss_duplicate, expiring_contracts,
                           filter_opportunities, find_duplicates, funnel, funnel_period, last_followups, merge_accounts,
                           money_progress, next_steps, opportunity_for_quote, set_funnel_period,
                           proposal_amounts, quote_amount, rename_account_projects, search_accounts, set_goals,
                           similar_accounts, win_opportunity)
from app.utils.reforestation import parse_date

# "Clientes" in the menu (docs/ANALISIS_ENCAJE_CRM.md, R7).
router = APIRouter(prefix="/clientes", tags=["clientes"])
templates.env.globals["crm_labels"] = LABELS

view_roles = deps.require_sales  # admin, ventas and a supervisor marked "También vende"
admin_only = deps.require_roles(ADMIN)


def toast_redirect(url: str, message: str, error: bool = False) -> RedirectResponse:
    response = RedirectResponse(url=url, status_code=status.HTTP_303_SEE_OTHER)
    response.set_cookie(key="toast_message", value=message)
    if error:
        response.set_cookie(key="toast_type", value="error")
    return response


def sellers(db: Session):
    """Who can own accounts and opportunities: admin, ventas and supervisors who also sell."""
    return db.query(User).filter((User.role.in_([ADMIN, VENTAS])) | ((User.role == SUPERVISOR) & (User.also_sells == True)),  # noqa: E712
                                 User.is_active != False).order_by(User.full_name).all()  # noqa: E712


def assignment_email(opportunity: Opportunity):
    """Subject and body for the seller an admin just assigned an opportunity to."""
    account = opportunity.account
    lines = [f"Te asignaron la oportunidad «{opportunity.title}» de {account.name}.", ""]
    if opportunity.next_step:
        when = f" ({opportunity.next_step_date:%d/%m/%Y})" if opportunity.next_step_date else ""
        lines.append(f"Próximo paso: {opportunity.next_step}{when}")
    lines.append(f"Ver en el sistema: https://tomatocr.com/clientes/oportunidades/{opportunity.id}")
    return f"Oportunidad asignada: {account.name}", "\n".join(lines)


def optional_date(value: Optional[str]) -> Optional[date]:
    return parse_date(value) if (value or "").strip() else None


def optional_int(value: Optional[str]) -> Optional[int]:
    return int(value) if (value or "").strip().isdigit() else None


def get_active_account(db: Session, account_id: int) -> Account:
    account = db.get(Account, account_id)
    if account is None or account.merged_into_id:
        raise HTTPException(status_code=404, detail="Cuenta no encontrada")
    return account


def editable_account(db: Session, account_id: int, user: User) -> Account:
    account = get_active_account(db, account_id)
    if not can_edit_account(user, account):
        raise HTTPException(status_code=403, detail="Esta cuenta tiene otro dueño")
    return account


def get_opportunity(db: Session, opportunity_id: int) -> Opportunity:
    opportunity = db.get(Opportunity, opportunity_id)
    if opportunity is None:
        raise HTTPException(status_code=404, detail="Oportunidad no encontrada")
    return opportunity


def editable_opportunity(db: Session, opportunity_id: int, user: User) -> Opportunity:
    opportunity = get_opportunity(db, opportunity_id)
    if not can_edit_opportunity(user, opportunity):
        raise HTTPException(status_code=403, detail="Esta oportunidad tiene otro dueño")
    return opportunity


def clean(value: Optional[str]) -> Optional[str]:
    return (value or "").strip() or None


# --- Filtro (the sales funnel) ------------------------------------------------------

@router.get("")
@router.get("/")
def pipeline(request: Request, motor: Optional[str] = None, owner: Optional[str] = None, stage: Optional[str] = None,
             q: Optional[str] = None, periodo: Optional[str] = None, origen: Optional[str] = None,
             db: Session = Depends(deps.get_db),
             user: User = Depends(view_roles)):
    owner_id = optional_int(owner)
    motor = motor if motor in MOTORS else None
    stage = stage if stage in STAGES else None
    origin = origen if origen in ORIGINS + ("sin_origen",) else None
    # Newest first; opportunities of discarded accounts live in "Descartados".
    opportunities = filter_opportunities(db.query(Opportunity), motor, owner_id, stage, q, origin).filter(
        ~Opportunity.account.has(Account.discarded_at.isnot(None))).order_by(Opportunity.id.desc()).all()
    period = funnel_period(db)
    whole_history = periodo == "todo"
    return templates.TemplateResponse("crm/embudo.html", {
        "request": request, "user": user,
        "funnel": funnel(db, motor, owner_id, None if whole_history else period, origin),
        "money_rows": money_progress(db, period, motor, owner_id, origin),
        "period": period, "whole_history": whole_history,
        "steps": next_steps(db, owner_id),
        "amounts": proposal_amounts(db, owner_id),
        "opportunities": [(o, quote_amount(db, o)) for o in opportunities],
        "sellers": sellers(db), "motors": MOTORS, "stages": STAGES, "funnel_stages": FUNNEL_STAGES, "goal_stages": GOAL_STAGES,
        "filters": {"motor": motor, "owner": owner_id, "stage": stage, "q": q or "", "origin": origin},
        "origins": ORIGINS,
        "duplicates": len(find_duplicates(db)) if user.role == ADMIN else 0,
        "discarded": discarded_count(db),
        "today": date.today(),
        "expiring": expiring_contracts(db),
    })


@router.get("/ayuda")
def guide(user: User = Depends(view_roles)):
    """The team guide moved to the manual (/manual/clientes); old links keep working."""
    return RedirectResponse(url="/manual/clientes", status_code=status.HTTP_301_MOVED_PERMANENTLY)


@router.post("/metas")
async def update_goals(request: Request, db: Session = Depends(deps.get_db), user: User = Depends(admin_only)):
    form = await request.form()
    targets = {}
    for stage in GOAL_STAGES + MONEY_GOALS:  # empty = no target
        value = (form.get(stage) or "").strip().replace(",", "").replace(".", "").replace("₡", "") or "0"
        if not value.isdigit():
            return toast_redirect("/clientes", "Las metas deben ser números enteros", error=True)
        targets[stage] = int(value)
    if form.get("period_start") or form.get("period_end"):
        try:
            start, end = parse_date(form.get("period_start") or ""), parse_date(form.get("period_end") or "")
            set_funnel_period(db, form.get("period_name") or "", start, end)
        except ValueError as e:
            return toast_redirect("/clientes", f"Periodo no válido: {e}", error=True)
    set_goals(db, targets)
    period = funnel_period(db)
    log_activity(db, user, "UPDATE", "CRM_GOALS", None, f"{targets}; periodo {period.label}")
    return toast_redirect("/clientes", "Metas y periodo actualizados")


# --- Cuentas ------------------------------------------------------------------------

@router.get("/cuentas")
def accounts(request: Request, q: Optional[str] = None, estado: Optional[str] = None, owner: Optional[str] = None,
             db: Session = Depends(deps.get_db), user: User = Depends(view_roles)):
    if estado == "descartada":
        return RedirectResponse(url="/clientes/descartados", status_code=status.HTTP_303_SEE_OTHER)
    owner_id = optional_int(owner)
    followups = last_followups(db)
    rows = []
    for account in reversed(active_accounts(db)):  # newest first
        if account.discarded_at or (owner_id and account.owner_id != owner_id):
            continue
        if q:
            needle = q.strip().lower()
            emails = [c.email or "" for c in account.contacts]
            if needle not in account.name.lower() and needle not in (account.tax_id or "") \
                    and not any(needle in e for e in emails):
                continue
        state = account_status(db, account)
        if estado and state != estado:
            continue
        rows.append({"account": account, "status": state, "last": followups.get(account.id),
                     "motors": sorted({o.motor for o in account.opportunities if o.motor})})
    return templates.TemplateResponse("crm/cuentas.html", {
        "request": request, "user": user, "rows": rows, "sellers": sellers(db),
        "filters": {"q": q or "", "estado": estado, "owner": owner_id},
        "duplicates": len(find_duplicates(db)) if user.role == ADMIN else 0,
        "discarded": discarded_count(db),
    })


def discarded_count(db: Session) -> int:
    return db.query(Account).filter(Account.merged_into_id.is_(None), Account.discarded_at.isnot(None)).count()


@router.get("/descartados")
def discarded(request: Request, db: Session = Depends(deps.get_db), user: User = Depends(view_roles)):
    """Accounts that won't move forward, newest discard first: reactivate them or (admin) delete them."""
    accounts = db.query(Account).filter(Account.merged_into_id.is_(None), Account.discarded_at.isnot(None)).order_by(
        Account.discarded_at.desc()).all()
    rows = [{"account": a, "blockers": delete_blockers(db, a),
             "motors": sorted({o.motor for o in a.opportunities if o.motor})} for a in accounts]
    return templates.TemplateResponse("crm/descartados.html", {
        "request": request, "user": user, "rows": rows, "discarded": len(rows),
        "duplicates": len(find_duplicates(db)) if user.role == ADMIN else 0,
    })


@router.get("/cuentas/nueva")
def new_account_form(request: Request, user: User = Depends(view_roles)):
    return templates.TemplateResponse("crm/cuenta_nueva.html", {
        "request": request, "user": user, "kinds": ACCOUNT_KINDS, "form": {}, "similar": []})


@router.post("/cuentas/nueva")
def create_account(
    request: Request,
    name: str = Form(...),
    kind: str = Form("otro"),
    tax_id: Optional[str] = Form(None),
    contact_name: Optional[str] = Form(None),
    contact_email: Optional[str] = Form(None),
    contact_phone: Optional[str] = Form(None),
    confirm: bool = Form(False),
    db: Session = Depends(deps.get_db),
    user: User = Depends(view_roles),
):
    form = {"name": name, "kind": kind, "tax_id": tax_id, "contact_name": contact_name,
            "contact_email": contact_email, "contact_phone": contact_phone}
    name, tax_id, email = name.strip(), clean(tax_id), (clean(contact_email) or "").lower() or None
    if not name:
        return toast_redirect("/clientes/cuentas/nueva", "Escriba el nombre de la cuenta", error=True)
    if tax_id and db.query(Account).filter(Account.tax_id == tax_id).first():
        confirm = False  # the same cédula can't exist twice
    similar = similar_accounts(db, name, tax_id, email)
    if similar and not confirm:
        return templates.TemplateResponse("crm/cuenta_nueva.html", {
            "request": request, "user": user, "kinds": ACCOUNT_KINDS, "form": form, "similar": similar,
            "tax_id_taken": bool(tax_id and any(a.tax_id == tax_id for a in similar)),
        })
    account = Account(name=name, kind=kind if kind in ACCOUNT_KINDS else "otro", tax_id=tax_id, owner_id=user.id,
                      created_by_id=user.id, source="manual")
    db.add(account)
    db.flush()
    if clean(contact_name) or email or clean(contact_phone):
        db.add(Contact(account_id=account.id, name=clean(contact_name) or email or clean(contact_phone), email=email,
                       phone=clean(contact_phone), is_primary=True, is_commercial=True))
    db.commit()
    log_activity(db, user, "CREATE", "ACCOUNT", account.id, f"Cuenta {account.name}")
    return toast_redirect(f"/clientes/cuentas/{account.id}", "Cuenta creada")


@router.get("/cuentas/{account_id}")
def account_file(account_id: int, request: Request, tab: str = "seguimientos",
                 db: Session = Depends(deps.get_db), user: User = Depends(view_roles)):
    account = db.get(Account, account_id)
    if account is None:
        raise HTTPException(status_code=404, detail="Cuenta no encontrada")
    if account.merged_into_id:
        return RedirectResponse(url=f"/clientes/cuentas/{account.merged_into_id}", status_code=status.HTTP_303_SEE_OTHER)
    projects = db.query(Project).filter(Project.account_id == account.id).order_by(Project.id).all()
    roles = db.query(ProjectContactRole).filter(ProjectContactRole.project_id.in_([p.id for p in projects])).all()
    contact_projects = {}
    project_names = {p.id: p.name for p in projects}
    for role in roles:
        contact_projects.setdefault(role.contact_id, []).append(
            {"project": project_names[role.project_id], "site": role.is_site, "reports": role.receives_reports})
    return templates.TemplateResponse("crm/cuenta.html", {
        "request": request, "user": user, "account": account, "status": account_status(db, account),
        "tab": tab if tab in ("seguimientos", "contactos", "oportunidades", "cotizaciones", "proyectos") else "seguimientos",
        "can_edit": can_edit_account(user, account),
        "contacts": account.contacts, "contact_projects": contact_projects,
        "opportunities": [(o, quote_amount(db, o)) for o in account.opportunities],
        "quotes": db.query(Quote).filter(Quote.account_id == account.id).order_by(Quote.fecha_emision.desc()).all(),
        "projects": projects,
        "reforestation": db.query(ReforestationProject).filter(ReforestationProject.account_id == account.id).all(),
        "activities": sorted(account.activities, key=lambda a: a.happened_at, reverse=True),
        "kinds": ACCOUNT_KINDS, "motors": MOTORS, "activity_types": [t for t in ACTIVITY_TYPES if t != "cambio_etapa"],
        "opportunity_kinds": OPPORTUNITY_KINDS, "origins": ORIGINS, "sellers": sellers(db), "today": date.today(),
    })


@router.post("/cuentas/{account_id}/editar")
def update_account(
    account_id: int,
    name: str = Form(...),
    kind: str = Form("otro"),
    legal_name: Optional[str] = Form(None),
    tax_id: Optional[str] = Form(None),
    source: Optional[str] = Form(None),
    province: Optional[str] = Form(None),
    address: Optional[str] = Form(None),
    website: Optional[str] = Form(None),
    vat_exemption_code: Optional[str] = Form(None),
    notes: Optional[str] = Form(None),
    db: Session = Depends(deps.get_db),
    user: User = Depends(view_roles),
):
    account = editable_account(db, account_id, user)
    url = f"/clientes/cuentas/{account.id}"
    tax_id = clean(tax_id)
    if tax_id and db.query(Account).filter(Account.tax_id == tax_id, Account.id != account.id).first():
        return toast_redirect(url, "Esa cédula ya está en otra cuenta", error=True)
    if not name.strip():
        return toast_redirect(url, "El nombre no puede quedar vacío", error=True)
    old_name = account.name
    account.name, account.kind = name.strip(), kind if kind in ACCOUNT_KINDS else account.kind
    renamed = rename_account_projects(db, account, old_name) if account.name != old_name else 0
    for attr, value in (("legal_name", legal_name), ("tax_id", tax_id), ("source", source), ("province", province),
                        ("address", address), ("website", website), ("vat_exemption_code", vat_exemption_code),
                        ("notes", notes)):
        setattr(account, attr, clean(value))
    claim_if_unowned(account, user)
    db.commit()
    log_activity(db, user, "UPDATE", "ACCOUNT", account.id,
                 f"Cuenta {account.name}" + (f" (antes {old_name}; {renamed} proyecto(s) actualizados)"
                                             if account.name != old_name else ""))
    return toast_redirect(url, "Datos guardados" + (f"; {renamed} proyecto(s) muestran el nombre nuevo" if renamed else ""))


@router.post("/cuentas/{account_id}/duenio")
def reassign_owner(account_id: int, owner_id: str = Form(""), db: Session = Depends(deps.get_db),
                   user: User = Depends(admin_only)):
    account = get_active_account(db, account_id)
    new_owner = db.get(User, int(owner_id)) if owner_id.isdigit() else None
    if owner_id and (new_owner is None or not new_owner.sells):
        return toast_redirect(f"/clientes/cuentas/{account.id}", "Ese usuario no puede ser dueño", error=True)
    account.owner_id = new_owner.id if new_owner else None
    db.commit()
    log_activity(db, user, "UPDATE", "ACCOUNT", account.id,
                 f"Dueño de {account.name}: {new_owner.full_name if new_owner else 'sin dueño'}")
    return toast_redirect(f"/clientes/cuentas/{account.id}", "Dueño actualizado")


@router.post("/cuentas/{account_id}/descartar")
def toggle_discard(account_id: int, reason: Optional[str] = Form(None), back: Optional[str] = Form(None),
                   db: Session = Depends(deps.get_db), user: User = Depends(view_roles)):
    """Discards the account (with a reason) or, if it already was, brings it back."""
    account = get_active_account(db, account_id)
    if user.role != ADMIN and account.owner_id != user.id:
        raise HTTPException(status_code=403, detail="Solo el dueño o un admin")
    url = f"/clientes/cuentas/{account.id}"
    if account.discarded_at:
        reactivate_account(db, account, user)
        db.commit()
        log_activity(db, user, "UPDATE", "ACCOUNT", account.id, f"Cuenta {account.name} reactivada")
        return toast_redirect("/clientes/descartados" if back == "descartados" else url,
                              f"{account.name} reactivada; sus oportunidades perdidas siguen así hasta que les cambies la etapa")
    try:
        discard_account(db, account, user, reason)
    except ValueError as e:
        return toast_redirect(url, str(e), error=True)
    db.commit()
    log_activity(db, user, "UPDATE", "ACCOUNT", account.id, f"Cuenta {account.name} descartada: {account.discard_reason}")
    return toast_redirect("/clientes/cuentas", f"{account.name} descartada; está en Descartados")


@router.post("/cuentas/{account_id}/borrar")
def delete_discarded(account_id: int, db: Session = Depends(deps.get_db), user: User = Depends(admin_only)):
    """Deletes for good a discarded account without real history (spam, tests)."""
    account = get_active_account(db, account_id)
    name = account.name
    try:
        delete_account(db, account)
    except ValueError as e:
        return toast_redirect("/clientes/descartados", str(e), error=True)
    db.commit()
    log_activity(db, user, "DELETE", "ACCOUNT", account_id, f"Cuenta descartada borrada: {name}")
    return toast_redirect("/clientes/descartados", f"{name} borrada")


# --- Contactos ----------------------------------------------------------------------

def save_contact(contact: Contact, name, role_title, email, phone, is_commercial, is_billing):
    contact.name = name.strip()
    contact.role_title, contact.phone = clean(role_title), clean(phone)
    contact.email = (clean(email) or "").lower() or None
    contact.is_commercial, contact.is_billing = is_commercial, is_billing


@router.post("/cuentas/{account_id}/contactos")
def add_contact(account_id: int, name: str = Form(...), role_title: Optional[str] = Form(None),
                email: Optional[str] = Form(None), phone: Optional[str] = Form(None),
                is_commercial: bool = Form(False), is_billing: bool = Form(False),
                db: Session = Depends(deps.get_db), user: User = Depends(view_roles)):
    account = editable_account(db, account_id, user)
    url = f"/clientes/cuentas/{account.id}?tab=contactos"
    if not name.strip():
        return toast_redirect(url, "Escriba el nombre del contacto", error=True)
    contact = Contact(account_id=account.id, is_primary=not account.contacts)
    save_contact(contact, name, role_title, email, phone, is_commercial, is_billing)
    db.add(contact)
    claim_if_unowned(account, user)
    db.commit()
    return toast_redirect(url, "Contacto agregado")


@router.post("/contactos/{contact_id}/editar")
def update_contact(contact_id: int, name: str = Form(...), role_title: Optional[str] = Form(None),
                   email: Optional[str] = Form(None), phone: Optional[str] = Form(None),
                   is_commercial: bool = Form(False), is_billing: bool = Form(False), is_primary: bool = Form(False),
                   db: Session = Depends(deps.get_db), user: User = Depends(view_roles)):
    contact = db.get(Contact, contact_id)
    if contact is None:
        raise HTTPException(status_code=404, detail="Contacto no encontrado")
    account = editable_account(db, contact.account_id, user)
    url = f"/clientes/cuentas/{account.id}?tab=contactos"
    if not name.strip():
        return toast_redirect(url, "El nombre no puede quedar vacío", error=True)
    save_contact(contact, name, role_title, email, phone, is_commercial, is_billing)
    if is_primary:
        for other in account.contacts:
            other.is_primary = other.id == contact.id
    claim_if_unowned(account, user)
    db.commit()
    return toast_redirect(url, "Contacto guardado")


@router.post("/contactos/{contact_id}/anonimizar")
def anonymize(contact_id: int, db: Session = Depends(deps.get_db), user: User = Depends(admin_only)):
    """When a person asks us to delete their data (derecho de supresión, /privacidad)."""
    contact = db.get(Contact, contact_id)
    if contact is None:
        raise HTTPException(status_code=404, detail="Contacto no encontrado")
    url = f"/clientes/cuentas/{contact.account_id}?tab=contactos"
    try:
        anonymize_contact(db, contact)
    except ValueError as e:
        return toast_redirect(url, str(e), error=True)
    db.commit()
    log_activity(db, user, "UPDATE", "CONTACT", contact.id, "Contacto anonimizado a pedido de la persona")
    return toast_redirect(url, "Datos del contacto eliminados; el historial de la cuenta se conserva")


# --- Oportunidades ------------------------------------------------------------------

@router.post("/cuentas/{account_id}/oportunidades")
def create_opportunity(account_id: int, title: str = Form(...), motor: Optional[str] = Form(None),
                       kind: str = Form("nuevo"), next_step: Optional[str] = Form(None),
                       next_step_date: Optional[str] = Form(None), amount_crc: Optional[str] = Form(None),
                       origin: Optional[str] = Form(None),
                       db: Session = Depends(deps.get_db), user: User = Depends(view_roles)):
    account = editable_account(db, account_id, user)
    url = f"/clientes/cuentas/{account.id}?tab=oportunidades"
    try:
        step_date = optional_date(next_step_date)
        amount = float(amount_crc.replace(",", "")) if clean(amount_crc) else None
    except ValueError as e:
        return toast_redirect(url, f"No se guardó: {e}", error=True)
    if not title.strip():
        return toast_redirect(url, "Escriba un título para la oportunidad", error=True)
    claim_if_unowned(account, user)
    opportunity = Opportunity(account_id=account.id, title=title.strip(), motor=motor if motor in MOTORS else None,
                              kind=kind if kind in OPPORTUNITY_KINDS else "nuevo", next_step=clean(next_step),
                              next_step_date=step_date, amount_crc=amount, owner_id=account.owner_id or user.id,
                              created_by_id=user.id, source="manual", origin=origin if origin in ORIGINS else None)
    db.add(opportunity)
    db.commit()
    log_activity(db, user, "CREATE", "OPPORTUNITY", opportunity.id, f"{opportunity.title} ({account.name})")
    return toast_redirect(f"/clientes/oportunidades/{opportunity.id}", "Oportunidad creada")


@router.post("/cuentas/{account_id}/cotizaciones/{quote_id}/oportunidad")
def opportunity_from_quote(account_id: int, quote_id: int, db: Session = Depends(deps.get_db),
                           user: User = Depends(view_roles)):
    """A quote saved before the Cotizador created opportunities gets its own, in Propuesta."""
    account = editable_account(db, account_id, user)
    quote = db.query(Quote).filter(Quote.id == quote_id, Quote.account_id == account.id).first()
    if quote is None:
        raise HTTPException(status_code=404, detail="Cotización no encontrada")
    if quote.opportunity_id:
        return toast_redirect(f"/clientes/oportunidades/{quote.opportunity_id}", "La cotización ya tiene oportunidad")
    claim_if_unowned(account, user)
    opportunity = opportunity_for_quote(db, quote, account, user)
    db.commit()
    return toast_redirect(f"/clientes/oportunidades/{opportunity.id}", "Oportunidad creada en Propuesta")


@router.get("/oportunidades/{opportunity_id}")
def opportunity_page(opportunity_id: int, request: Request, db: Session = Depends(deps.get_db),
                     user: User = Depends(view_roles)):
    opportunity = get_opportunity(db, opportunity_id)
    account = db.get(Account, opportunity.account_id)
    linked_project = db.get(Project, opportunity.project_id) if opportunity.project_id else None
    return templates.TemplateResponse("crm/oportunidad.html", {
        "request": request, "user": user, "opportunity": opportunity, "account": account,
        "can_edit": can_edit_opportunity(user, opportunity),
        "amount": quote_amount(db, opportunity),
        "quotes": db.query(Quote).filter(Quote.opportunity_id == opportunity.id).order_by(Quote.fecha_emision.desc()).all(),
        "activities": db.query(CrmActivity).filter(CrmActivity.opportunity_id == opportunity.id).order_by(
            CrmActivity.happened_at.desc()).all(),
        "stages": STAGES, "motors": MOTORS, "origins": ORIGINS, "sellers": sellers(db),
        "activity_types": [t for t in ACTIVITY_TYPES if t != "cambio_etapa"], "today": date.today(),
        "linked_project": linked_project,
        "account_projects": db.query(Project).filter(
            (Project.account_id == account.id) | (Project.account_id.is_(None))).order_by(Project.name).all(),
    })


@router.post("/oportunidades/{opportunity_id}/editar")
def update_opportunity(opportunity_id: int, background: BackgroundTasks, title: str = Form(...), motor: Optional[str] = Form(None),
                       next_step: Optional[str] = Form(None), next_step_date: Optional[str] = Form(None),
                       expected_close_date: Optional[str] = Form(None), amount_crc: Optional[str] = Form(None),
                       owner_id: Optional[str] = Form(None), origin: Optional[str] = Form(None),
                       db: Session = Depends(deps.get_db), user: User = Depends(view_roles)):
    opportunity = editable_opportunity(db, opportunity_id, user)
    url = f"/clientes/oportunidades/{opportunity.id}"
    try:
        step_date, close_date = optional_date(next_step_date), optional_date(expected_close_date)
        amount = float(amount_crc.replace(",", "")) if clean(amount_crc) else None
    except ValueError as e:
        return toast_redirect(url, f"No se guardó: {e}", error=True)
    if not title.strip():
        return toast_redirect(url, "El título no puede quedar vacío", error=True)
    opportunity.title, opportunity.motor = title.strip(), motor if motor in MOTORS else None
    opportunity.next_step, opportunity.next_step_date = clean(next_step), step_date
    opportunity.expected_close_date, opportunity.amount_crc = close_date, amount
    if origin is not None:
        opportunity.origin = origin if origin in ORIGINS else None
    new_owner = None
    if user.role == ADMIN and owner_id is not None:
        new_id = optional_int(owner_id)
        if new_id and new_id not in {s.id for s in sellers(db)}:
            return toast_redirect(url, "Ese usuario no puede ser vendedor", error=True)
        if new_id != opportunity.owner_id:
            new_owner = db.get(User, new_id) if new_id else None
            opportunity.owner_id = new_id
    claim_if_unowned(opportunity, user)
    db.commit()
    if new_owner is not None:
        log_activity(db, user, "UPDATE", "OPPORTUNITY", opportunity.id,
                     f"Oportunidad {opportunity.title} asignada a {new_owner.full_name}")
        if new_owner.id != user.id:
            background.add_task(send_plain_email, [new_owner.email], *assignment_email(opportunity))
    return toast_redirect(url, "Oportunidad guardada")


@router.post("/oportunidades/{opportunity_id}/descartar")
def discard_from_opportunity(opportunity_id: int, reason: Optional[str] = Form(None),
                             db: Session = Depends(deps.get_db), user: User = Depends(view_roles)):
    """'Descartar cliente' from the opportunity: the whole account goes to Descartados."""
    opportunity = get_opportunity(db, opportunity_id)
    account = get_active_account(db, opportunity.account_id)
    if user.role != ADMIN and user.id not in (account.owner_id, opportunity.owner_id):
        raise HTTPException(status_code=403, detail="Solo el dueño o un admin")
    url = f"/clientes/oportunidades/{opportunity.id}"
    if account.discarded_at:
        return toast_redirect(url, "La cuenta ya está descartada", error=True)
    try:
        discard_account(db, account, user, reason)
    except ValueError as e:
        return toast_redirect(url, str(e), error=True)
    db.commit()
    log_activity(db, user, "UPDATE", "ACCOUNT", account.id, f"Cuenta {account.name} descartada: {account.discard_reason}")
    return toast_redirect("/clientes", f"{account.name} descartada; está en Descartados")


@router.post("/oportunidades/{opportunity_id}/etapa")
def update_stage(opportunity_id: int, stage: str = Form(...), lost_reason: Optional[str] = Form(None),
                 db: Session = Depends(deps.get_db), user: User = Depends(view_roles)):
    opportunity = editable_opportunity(db, opportunity_id, user)
    url = f"/clientes/oportunidades/{opportunity.id}"
    try:
        change_stage(db, opportunity, stage, user, lost_reason)
    except ValueError as e:
        return toast_redirect(url, str(e), error=True)
    claim_if_unowned(opportunity, user)
    db.commit()
    return toast_redirect(url, f"Etapa: {LABELS['stage'][stage]}")


@router.post("/oportunidades/{opportunity_id}/ganada")
def mark_won(opportunity_id: int, project_id: str = Form(...), db: Session = Depends(deps.get_db),
             user: User = Depends(admin_only)):
    """Links an existing project and marks the opportunity as won. To create a new project,
    the page links to /projects/new?opportunity_id=... instead."""
    opportunity = get_opportunity(db, opportunity_id)
    url = f"/clientes/oportunidades/{opportunity.id}"
    project = db.get(Project, int(project_id)) if project_id.isdigit() else None
    if project is None:
        return toast_redirect(url, "Elegí el proyecto", error=True)
    try:
        win_opportunity(db, opportunity, project, user)
    except ValueError as e:
        return toast_redirect(url, str(e), error=True)
    db.commit()
    return toast_redirect(url, f"Oportunidad ganada: ligada a {project.name}")


@router.post("/proyectos/{project_id}/renovacion")
def renewal(project_id: int, db: Session = Depends(deps.get_db), user: User = Depends(view_roles)):
    project = db.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Proyecto no encontrado")
    account = db.get(Account, project.account_id) if project.account_id else None
    if account is None:
        return toast_redirect("/clientes", "El proyecto no tiene cuenta", error=True)
    if not can_edit_account(user, account):
        raise HTTPException(status_code=403, detail="Esta cuenta tiene otro dueño")
    opportunity = create_renewal(db, project, user)
    db.commit()
    return toast_redirect(f"/clientes/oportunidades/{opportunity.id}", "Renovación creada")


# --- API for the account pickers (project form and quote tool) -----------------------

@router.get("/api/cuentas")
def api_search_accounts(q: str = "", db: Session = Depends(deps.get_db), user: User = Depends(view_roles)):
    return [account_payload(a) for a in search_accounts(db, q)]


@router.get("/api/cuentas/{account_id}")
def api_account(account_id: int, db: Session = Depends(deps.get_db), user: User = Depends(view_roles)):
    return account_payload(get_active_account(db, account_id))


@router.post("/api/cuentas")
def api_create_account(payload: dict = Body(...), db: Session = Depends(deps.get_db), user: User = Depends(view_roles)):
    """Creates an account from a picker. Answers 409 with the similar accounts unless confirm is true."""
    name = (payload.get("name") or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="Escriba el nombre de la cuenta")
    kind = payload.get("kind") if payload.get("kind") in ACCOUNT_KINDS else "otro"
    similar = similar_accounts(db, name)
    if similar and not payload.get("confirm"):
        return JSONResponse(status_code=409, content={"similar": [account_payload(a) for a in similar]})
    account = Account(name=name, kind=kind, owner_id=user.id, created_by_id=user.id, source="manual")
    db.add(account)
    db.commit()
    log_activity(db, user, "CREATE", "ACCOUNT", account.id, f"Cuenta {account.name}")
    return account_payload(account)


@router.post("/api/cuentas/{account_id}/contactos")
def api_add_contact(account_id: int, payload: dict = Body(...), db: Session = Depends(deps.get_db),
                    user: User = Depends(view_roles)):
    account = editable_account(db, account_id, user)
    name = (payload.get("name") or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="Escriba el nombre del contacto")
    contact = Contact(account_id=account.id, is_primary=not account.contacts)
    save_contact(contact, name, payload.get("role_title"), payload.get("email"), payload.get("phone"),
                 bool(payload.get("is_commercial")), bool(payload.get("is_billing")))
    db.add(contact)
    claim_if_unowned(account, user)
    db.commit()
    db.refresh(account)
    return {"contact": {"id": contact.id, "name": contact.name, "email": contact.email, "phone": contact.phone,
                        "role_title": contact.role_title, "is_primary": contact.is_primary},
            "account": account_payload(account)}


@router.get("/api/oportunidades/{opportunity_id}")
def api_opportunity(opportunity_id: int, db: Session = Depends(deps.get_db), user: User = Depends(view_roles)):
    opportunity = get_opportunity(db, opportunity_id)
    return {"id": opportunity.id, "title": opportunity.title, "stage": opportunity.stage,
            "account": account_payload(db.get(Account, opportunity.account_id))}


# --- Seguimientos -------------------------------------------------------------------

@router.post("/cuentas/{account_id}/seguimientos")
def add_followup(account_id: int, type: str = Form(...), happened_at: Optional[str] = Form(None),
                 notes: Optional[str] = Form(None), opportunity_id: Optional[str] = Form(None),
                 contact_id: Optional[str] = Form(None), next_step: Optional[str] = Form(None),
                 next_step_date: Optional[str] = Form(None), back: Optional[str] = Form(None),
                 db: Session = Depends(deps.get_db), user: User = Depends(view_roles)):
    account = editable_account(db, account_id, user)
    url = back if (back or "").startswith("/clientes/") else f"/clientes/cuentas/{account.id}"
    if type not in ACTIVITY_TYPES or type == "cambio_etapa":
        return toast_redirect(url, "Tipo de seguimiento no válido", error=True)
    try:
        day = optional_date(happened_at) or date.today()
        step_date = optional_date(next_step_date)
    except ValueError as e:
        return toast_redirect(url, f"No se guardó: {e}", error=True)
    if day > date.today():
        return toast_redirect(url, "No se guardó: la fecha no puede ser futura; use el próximo paso", error=True)
    opportunity = None
    if optional_int(opportunity_id):
        opportunity = db.get(Opportunity, optional_int(opportunity_id))
        if opportunity is None or opportunity.account_id != account.id:
            return toast_redirect(url, "Esa oportunidad no es de esta cuenta", error=True)
    contact = db.get(Contact, optional_int(contact_id)) if optional_int(contact_id) else None
    if contact is not None and contact.account_id != account.id:
        contact = None
    happened = datetime.combine(day, datetime.utcnow().time()) if day == date.today() else datetime.combine(day, datetime.min.time())
    db.add(CrmActivity(account_id=account.id, opportunity_id=opportunity.id if opportunity else None,
                       contact_id=contact.id if contact else None, type=type, happened_at=happened,
                       notes=clean(notes), user_id=user.id))
    if opportunity is not None and (clean(next_step) or step_date):
        if can_edit_opportunity(user, opportunity):
            opportunity.next_step, opportunity.next_step_date = clean(next_step), step_date
            claim_if_unowned(opportunity, user)
    claim_if_unowned(account, user)
    db.commit()
    return toast_redirect(url, f"Seguimiento registrado: {LABELS['activity'][type]}")


# --- Duplicados (admin) -------------------------------------------------------------

def account_summary(db: Session, account: Account) -> dict:
    return {
        "account": account,
        "contacts": db.query(Contact).filter(Contact.account_id == account.id).count(),
        "opportunities": db.query(Opportunity).filter(Opportunity.account_id == account.id).count(),
        "projects": [p.name for p in db.query(Project).filter(Project.account_id == account.id)],
        "quotes": db.query(Quote).filter(Quote.account_id == account.id).count(),
        "reforestation": db.query(ReforestationProject).filter(ReforestationProject.account_id == account.id).count(),
    }


@router.get("/duplicados")
def duplicates(request: Request, db: Session = Depends(deps.get_db), user: User = Depends(admin_only)):
    pairs = [
        {"a": account_summary(db, a), "b": account_summary(db, b), "score": score}
        for a, b, score in find_duplicates(db)
    ]
    return templates.TemplateResponse("crm/duplicados.html", {"request": request, "user": user, "pairs": pairs})


@router.post("/cuentas/{keep_id}/fusionar/{drop_id}")
def merge(keep_id: int, drop_id: int, db: Session = Depends(deps.get_db), user: User = Depends(admin_only)):
    keep, drop = get_active_account(db, keep_id), get_active_account(db, drop_id)
    try:
        moved = merge_accounts(db, keep, drop, user)
    except ValueError as e:
        return toast_redirect("/clientes/duplicados", str(e), error=True)
    total = sum(moved.values())
    return toast_redirect("/clientes/duplicados", f"'{drop.name}' se fusionó en '{keep.name}' ({total} registros movidos)")


@router.post("/duplicados/{a_id}/{b_id}/descartar")
def not_duplicate(a_id: int, b_id: int, db: Session = Depends(deps.get_db), user: User = Depends(admin_only)):
    get_active_account(db, a_id), get_active_account(db, b_id)
    dismiss_duplicate(db, a_id, b_id, user)
    db.commit()
    return toast_redirect("/clientes/duplicados", "Marcadas como cuentas distintas")


# --- Asignación de oportunidades -------------------------------------------------------

@router.get("/asignacion")
def assignment(request: Request, db: Session = Depends(deps.get_db), user: User = Depends(admin_only)):
    rows = {row.motor: row.user_id for row in db.query(CrmAssignment).all()}
    motors = [(m, LABELS["motor"][m]) for m in MOTORS] + [(ASSIGNMENT_DEFAULT, "Cualquier otro / sin motor")]
    return templates.TemplateResponse("crm/asignacion.html", {
        "request": request, "user": user, "motors": motors, "rows": rows, "sellers": sellers(db),
    })


@router.post("/asignacion")
async def update_assignment(request: Request, db: Session = Depends(deps.get_db), user: User = Depends(admin_only)):
    form = await request.form()
    valid = {s.id for s in sellers(db)}
    changes = []
    for motor in list(MOTORS) + [ASSIGNMENT_DEFAULT]:
        user_id = optional_int(form.get(motor))
        user_id = user_id if user_id in valid else None
        row = db.get(CrmAssignment, motor)
        if row is None:
            row = CrmAssignment(motor=motor)
            db.add(row)
        if row.user_id != user_id:
            changes.append(motor)
        row.user_id = user_id
    db.commit()
    if changes:
        log_activity(db, user, "UPDATE", "CRM_ASSIGNMENT", None, "Asignación de oportunidades: " + ", ".join(changes))
    return toast_redirect("/clientes/asignacion", "Asignación guardada")
