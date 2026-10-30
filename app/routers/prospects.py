"""Posibles clientes (/clientes/posibles): the sellers' prospecting list (app/utils/prospects.py).
Every seller sees all of it; its seller and the admin change each one."""
import math
from datetime import date, datetime
from typing import Dict, Optional

from fastapi import APIRouter, Depends, Form, HTTPException, Request, status
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.core.roles import ADMIN
from app.core.templates import templates
from app.db.models.crm import ACCOUNT_KINDS, MOTORS, Account
from app.db.models.prospect import CHANNELS, PROVINCES, SOURCES, STATUSES, Prospect
from app.db.models.user import User
from app.routers import deps
from app.routers.crm import discarded_count, sellers
from app.routers.suppliers import whatsapp_url  # noqa: F401 (registers the template global)
from app.utils import prospects as P
from app.utils.activity import log_activity
from app.utils.crm import similar_accounts
from app.utils.timecr import today_cr

router = APIRouter(prefix="/clientes/posibles", tags=["clientes"])
view_roles = deps.require_sales
FIELDS = ("company", "contact_name", "contact_role", "phone", "email", "kind", "motor", "province", "source", "notes",
          "next_contact_date")

templates.env.globals["prospect_labels"] = {"status": STATUSES, "source": SOURCES, "channel": CHANNELS,
                                            "provinces": PROVINCES, "views": P.VIEWS}


def toast_redirect(url: str, message: str, error: bool = False) -> RedirectResponse:
    response = RedirectResponse(url=url, status_code=status.HTTP_303_SEE_OTHER)
    response.set_cookie(key="toast_message", value=message)
    if error:
        response.set_cookie(key="toast_type", value="error")
    return response


def get_prospect(db: Session, prospect_id: int) -> Prospect:
    prospect = db.get(Prospect, prospect_id)
    if prospect is None:
        raise HTTPException(status_code=404, detail="Posible cliente no encontrado")
    return prospect


def editable(db: Session, prospect_id: int, user: User) -> Prospect:
    prospect = get_prospect(db, prospect_id)
    if not P.can_edit(user, prospect):
        raise HTTPException(status_code=403, detail="Este posible cliente lo trabaja otro vendedor")
    return prospect


def page_url(prospect: Prospect) -> str:
    return f"/clientes/posibles/{prospect.id}"


def render_list(request: Request, db: Session, user: User, params: Dict, form: Optional[Dict] = None,
                error: Optional[str] = None, found: Optional[Dict] = None):
    today = today_cr()
    view = params.get("vista") if params.get("vista") in P.VIEWS else "abiertos"
    seller = params.get("vendedor") or ("todos" if user.role == ADMIN else str(user.id))
    owner_id = int(seller) if seller.isdigit() else None
    rows = P.listing(db, today, view, owner_id, params.get("q") or "", params.get("motor") or "",
                     params.get("provincia") or "")
    pages = max(1, math.ceil(len(rows) / P.PER_PAGE))
    page = min(max(int(params.get("page") or 1) if str(params.get("page") or "1").isdigit() else 1, 1), pages)
    filters = {"vista": view, "vendedor": seller, "q": params.get("q") or "", "motor": params.get("motor") or "",
               "provincia": params.get("provincia") or ""}
    return templates.TemplateResponse("crm/posibles.html", {
        "request": request, "user": user, "rows": rows[(page - 1) * P.PER_PAGE:page * P.PER_PAGE], "found": len(rows),
        "page": page, "pages": pages, "filters": filters, "today": today, "sellers": sellers(db),
        "kinds": ACCOUNT_KINDS, "motors": MOTORS, "form": form or {}, "error": error, "repeats": found,
        "week": P.week_summary(db, today, None if owner_id is None else owner_id),
        "my_due": P.due_count(db, user.id, today), "can_edit": lambda p: P.can_edit(user, p), "due": P.due,
        "discarded": discarded_count(db), "duplicates": 0,
    }, status_code=400 if error else 200)


@router.get("")
@router.get("/")
def prospects_page(request: Request, db: Session = Depends(deps.get_db), user: User = Depends(view_roles)):
    return render_list(request, db, user, dict(request.query_params))


@router.post("/nuevo")
async def create_prospect(request: Request, db: Session = Depends(deps.get_db), user: User = Depends(view_roles)):
    form = {key: value for key, value in (await request.form()).items()}
    try:
        fields = P.parse_fields(form)
    except ValueError as e:
        return render_list(request, db, user, {}, form=form, error=str(e))
    found = P.repeats(db, fields)
    if (found["accounts"] or found["prospects"]) and not form.get("confirm"):
        return render_list(request, db, user, {}, form=form, found=found,
                           error="Puede que ya exista. Revisá la lista de abajo antes de guardarlo.")
    prospect = Prospect(created_by_id=user.id, owner_id=user.id if user.sells else None, **fields)
    if user.role == ADMIN and str(form.get("owner_id") or "").isdigit():
        prospect.owner_id = int(form["owner_id"]) if int(form["owner_id"]) in {s.id for s in sellers(db)} else prospect.owner_id
    db.add(prospect)
    db.commit()
    log_activity(db, user, "CREATE", "PROSPECT", prospect.id, prospect.company)
    return toast_redirect("/clientes/posibles", f"«{prospect.company}» agregado a Posibles clientes")


@router.get("/{prospect_id}")
def prospect_page(prospect_id: int, request: Request, db: Session = Depends(deps.get_db), user: User = Depends(view_roles)):
    prospect = get_prospect(db, prospect_id)
    return templates.TemplateResponse("crm/posible.html", {
        "request": request, "user": user, "p": prospect, "today": today_cr(), "kinds": ACCOUNT_KINDS, "motors": MOTORS,
        "sellers": sellers(db), "editable": P.can_edit(user, prospect), "due": P.due,
        "similar": P.similar_prospects(db, prospect.company, prospect.phone, prospect.email, prospect.id),
        "similar_accounts": similar_accounts(db, prospect.company, None, prospect.email) if prospect.is_open else [],
    })


@router.post("/{prospect_id}/editar")
async def edit_prospect(prospect_id: int, request: Request, db: Session = Depends(deps.get_db),
                        user: User = Depends(view_roles)):
    prospect = editable(db, prospect_id, user)
    form = {key: value for key, value in (await request.form()).items()}
    try:
        fields = P.parse_fields(form)
    except ValueError as e:
        return toast_redirect(page_url(prospect), str(e), error=True)
    for key, value in fields.items():
        setattr(prospect, key, value)
    owner = str(form.get("owner_id") or "")
    if user.role == ADMIN and "owner_id" in form:
        prospect.owner_id = int(owner) if owner.isdigit() and int(owner) in {s.id for s in sellers(db)} else None
    elif prospect.owner_id is None:
        prospect.owner_id = user.id
    db.commit()
    return toast_redirect(page_url(prospect), "Guardado")


@router.post("/{prospect_id}/intento")
def add_attempt(prospect_id: int, channel: str = Form("llamada"), notes: str = Form(""), next_contact_date: str = Form(""),
                back: str = Form(""), db: Session = Depends(deps.get_db), user: User = Depends(view_roles)):
    prospect = editable(db, prospect_id, user)
    url = "/clientes/posibles" if back == "lista" else page_url(prospect)
    if not prospect.is_open:
        return toast_redirect(url, "Ese posible cliente ya está cerrado", error=True)
    try:
        next_date = date.fromisoformat(next_contact_date) if next_contact_date else None
    except ValueError:
        return toast_redirect(url, "Revisá la fecha del próximo intento", error=True)
    P.add_attempt(prospect, user, channel, notes, next_date)
    db.commit()
    when = f"; próximo intento el {next_date:%d/%m/%Y}" if next_date else ""
    return toast_redirect(url, f"Intento registrado con {prospect.company}{when}")


@router.post("/{prospect_id}/convertir")
def convert(prospect_id: int, request: Request, account_id: str = Form(""), new_account: str = Form(""),
            db: Session = Depends(deps.get_db), user: User = Depends(view_roles)):
    prospect = editable(db, prospect_id, user)
    if not prospect.is_open:
        if prospect.opportunity_id:
            return toast_redirect(f"/clientes/oportunidades/{prospect.opportunity_id}", "Ya estaba convertido")
        return toast_redirect(page_url(prospect), "Reactivalo antes de convertirlo", error=True)
    account = None
    if account_id.isdigit():
        account = db.get(Account, int(account_id))
        if account is None or account.merged_into_id or account.discarded_at:
            return toast_redirect(page_url(prospect), "Esa cuenta ya no está activa", error=True)
    elif not new_account:
        similar = similar_accounts(db, prospect.company, None, prospect.email)
        if similar:
            return templates.TemplateResponse("crm/posible_convertir.html", {
                "request": request, "user": user, "p": prospect, "similar": similar})
    opportunity = P.convert(db, prospect, user, account)
    db.commit()
    return toast_redirect(f"/clientes/oportunidades/{opportunity.id}",
                          f"«{prospect.company}» pasó al Filtro como oportunidad en Nueva")


@router.post("/{prospect_id}/descartar")
def discard(prospect_id: int, reason: str = Form(""), back: str = Form(""), db: Session = Depends(deps.get_db),
            user: User = Depends(view_roles)):
    prospect = editable(db, prospect_id, user)
    url = "/clientes/posibles" if back == "lista" else page_url(prospect)
    if not reason.strip():
        return toast_redirect(url, "Escribí por qué no le interesa", error=True)
    if prospect.is_open:
        prospect.status, prospect.discard_reason, prospect.next_contact_date = "descartado", reason.strip(), None
        prospect.owner_id = prospect.owner_id or user.id
        db.commit()
    return toast_redirect(url, f"«{prospect.company}» pasó a No le interesa")


@router.post("/{prospect_id}/reactivar")
def reactivate(prospect_id: int, db: Session = Depends(deps.get_db), user: User = Depends(view_roles)):
    prospect = editable(db, prospect_id, user)
    if prospect.status == "descartado":
        prospect.status = "en_seguimiento" if prospect.attempts else "por_contactar"
        prospect.discard_reason = None
        db.commit()
    return toast_redirect(page_url(prospect), "Reactivado: vuelve a la lista")


@router.post("/{prospect_id}/borrar")
def delete(prospect_id: int, db: Session = Depends(deps.get_db), user: User = Depends(view_roles)):
    prospect = editable(db, prospect_id, user)
    if prospect.status == "convertido":
        return toast_redirect(page_url(prospect), "Uno convertido no se borra: ya es una cuenta", error=True)
    company = prospect.company
    db.delete(prospect)
    db.commit()
    log_activity(db, user, "DELETE", "PROSPECT", prospect_id, company)
    return toast_redirect("/clientes/posibles", f"«{company}» borrado")
