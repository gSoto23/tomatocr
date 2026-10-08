import os
import re
from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status, Request
from fastapi.responses import JSONResponse, Response
from sqlalchemy.orm import Session

from app.core.templates import templates
from app.db.models.crm import Account, Opportunity
from app.db.models.user import User
from app.db.models.quote import Quote, QuoteEmail
from app.routers import deps
from app.core.roles import ADMIN, CLIENT, QUOTES_ROLES, VENTAS
from app.utils.activity import log_activity
from app.utils.crm import CLOSED_STAGES, account_of_client_user, advance_to_proposal
from app.utils.email import send_quote_email
from app.utils.quote_pdf import default_email, pdf_filename, quote_pdf
from app.utils.timecr import CR_OFFSET, now_cr, today_cr

router = APIRouter(
    tags=["quotes"],
    dependencies=[Depends(deps.require_quotes)]
)

def check_quotes_access(user: User):
    # Same rule as the menu (base_dashboard.html): whoever sells, and the client.
    if not deps.can_quote(user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized")


def visible_quotes(db: Session, user: User):
    """Admin and ventas see every quote; a client only the quotes of its own account."""
    query = db.query(Quote)
    if user.role == CLIENT:
        account = account_of_client_user(db, user)
        query = query.filter(Quote.account_id == (account.id if account else -1))
    return query


def opportunity_title(q: Quote):
    from sqlalchemy.orm import object_session
    if not q.opportunity_id or object_session(q) is None:
        return None
    opp = object_session(q).get(Opportunity, q.opportunity_id)
    return opp.title if opp else None


def serialize(q: Quote, account_names: dict) -> dict:
    return {
        "id": q.id,
        "numero_cotizacion": q.numero_cotizacion,
        "cliente_nombre": q.cliente_nombre,
        "fecha_emision": str(q.fecha_emision),
        "total": q.total,
        "moneda": q.moneda,
        "cliente_datos": q.cliente_datos,
        "tipo_servicio": q.tipo_servicio,
        "frecuencia": q.frecuencia,
        "validez_dias": q.validez_dias,
        "notes": q.notes,
        "terminos": q.terminos,
        "iva": q.iva,
        "subtotal": q.subtotal,
        "discount": q.discount or 0.0,
        "tax_rate": q.tax_rate if q.tax_rate is not None else 13.0,
        "items": q.items,
        "account_id": q.account_id,
        "account_name": account_names.get(q.account_id),
        "opportunity_id": q.opportunity_id,
        "opportunity_title": opportunity_title(q),
        "last_sent_at": last_sent_at(q),
    }


def last_sent_at(q: Quote):
    from sqlalchemy.orm import object_session
    session = object_session(q)
    if session is None:
        return None
    row = session.query(QuoteEmail.sent_at).filter(QuoteEmail.quote_id == q.id).order_by(QuoteEmail.sent_at.desc()).first()
    return (row[0] - CR_OFFSET).date().isoformat() if row else None


def number(value, default: float) -> float:
    try:
        return max(0.0, float(value))
    except (TypeError, ValueError):
        return default


def account_names(db: Session, quotes) -> dict:
    ids = {q.account_id for q in quotes if q.account_id}
    return {a.id: a.name for a in db.query(Account).filter(Account.id.in_(ids))} if ids else {}

@router.get("/cotizador", response_class=JSONResponse)
def view_cotizador(request: Request, user: User = Depends(deps.get_current_user)):
    check_quotes_access(user)
    # Render the template
    return templates.TemplateResponse("cotizador/index.html", {"request": request, "user": user,
                                                             "picks_account": user.role != CLIENT,
                                                             "can_delete": user.role == ADMIN,
                                                             "can_send": user.sells,
                                                             "asset_version": ASSET_VERSION})

@router.get("/api/quotes/next-number")
def get_next_quote_number(db: Session = Depends(deps.get_db), user: User = Depends(deps.get_current_user)):
    check_quotes_access(user)
    return {"next_number": next_quote_sequence(db)}


# Changes with every deploy, so browsers never keep an old copy of the quote tool.
ASSET_VERSION = int(max(os.path.getmtime(f"app/static/cotizador/{name}") for name in ("app.js", "style.css")))

QUOTE_NUMBER_RE = re.compile(r"^TCR-(\d{4})-(\d+)$")


def next_quote_sequence(db: Session, year: Optional[int] = None) -> int:
    """Next sequence of the year after the highest TCR-YYYY-NNNN in use (every account),
    so a deleted quote can't make two quotes share a number."""
    year = year or date.today().year
    highest = 0
    for (number,) in db.query(Quote.numero_cotizacion).filter(Quote.numero_cotizacion.like(f"TCR-{year}-%")):
        match = QUOTE_NUMBER_RE.match(number or "")
        if match:
            highest = max(highest, int(match.group(2)))
    return highest + 1

@router.get("/api/quotes/")
def list_quotes(
    db: Session = Depends(deps.get_db),
    user: User = Depends(deps.get_current_user),
    limit: int = 20
):
    check_quotes_access(user)
    quotes = visible_quotes(db, user).order_by(Quote.created_at.desc()).limit(limit).all()
    names = account_names(db, quotes)
    return [serialize(q, names) for q in quotes]

HISTORY_PAGE_SIZE = 10


@router.get("/api/quotes/historial")
def quote_history(q: str = "", estado: str = "", desde: str = "", hasta: str = "", page: int = 1,
                  db: Session = Depends(deps.get_db), user: User = Depends(deps.get_current_user)):
    """The quote tool's history: search by number, client or account, sent or not, issue dates,
    newest first, 10 per page."""
    check_quotes_access(user)
    query = visible_quotes(db, user)
    text = q.strip()
    if text:
        like = f"%{text}%"
        matching_accounts = db.query(Account.id).filter(Account.name.ilike(like))
        query = query.filter((Quote.numero_cotizacion.ilike(like)) | (Quote.cliente_nombre.ilike(like))
                             | (Quote.account_id.in_(matching_accounts)))
    sent_ids = db.query(QuoteEmail.quote_id)
    if estado == "enviadas":
        query = query.filter(Quote.id.in_(sent_ids))
    elif estado == "sin_enviar":
        query = query.filter(~Quote.id.in_(sent_ids))
    for value, compare in ((desde, Quote.fecha_emision.__ge__), (hasta, Quote.fecha_emision.__le__)):
        try:
            query = query.filter(compare(date.fromisoformat(value))) if value else query
        except ValueError:
            raise HTTPException(status_code=400, detail="Fecha no válida")
    total = query.count()
    pages = max(1, -(-total // HISTORY_PAGE_SIZE))
    page = min(max(1, page), pages)
    quotes = query.order_by(Quote.fecha_emision.desc(), Quote.id.desc()).offset(
        (page - 1) * HISTORY_PAGE_SIZE).limit(HISTORY_PAGE_SIZE).all()
    names = account_names(db, quotes)
    return {"items": [serialize(x, names) for x in quotes], "total": total, "page": page, "pages": pages}


@router.get("/api/quotes/{id}")
def get_quote(id: int, db: Session = Depends(deps.get_db), user: User = Depends(deps.get_current_user)):
    check_quotes_access(user)
    q = visible_quotes(db, user).filter(Quote.id == id).first()
    if not q:
        raise HTTPException(status_code=404, detail="Cotización no encontrada")
    return serialize(q, account_names(db, [q]))

@router.delete("/api/quotes/{id}")
def delete_quote(id: int, db: Session = Depends(deps.get_db), user: User = Depends(deps.get_current_user)):
    """Only the admin deletes a quote (made by mistake); it is recorded in Actividad."""
    if user.role != ADMIN:
        raise HTTPException(status_code=403, detail="Solo el admin puede borrar cotizaciones")
    q = db.query(Quote).filter(Quote.id == id).first()
    if not q:
        raise HTTPException(status_code=404, detail="Cotización no encontrada")
    number, client = q.numero_cotizacion, q.cliente_nombre
    db.query(QuoteEmail).filter(QuoteEmail.quote_id == q.id).delete()
    db.delete(q)
    db.commit()
    log_activity(db, user=user, action="DELETE", entity_type="QUOTE", entity_id=id,
                 details=f"Borró la cotización {number} ({client})")
    return {"ok": True}


@router.post("/api/quotes/")
async def upsert_quote(request: Request, db: Session = Depends(deps.get_db), user: User = Depends(deps.get_current_user)):
    check_quotes_access(user)
    data = await request.json()
    numero_cotizacion = data.get("numero_cotizacion")
    
    if not numero_cotizacion:
        raise HTTPException(status_code=400, detail="numero_cotizacion es requerido")
        
    from datetime import datetime
    try:
        issue_date = datetime.strptime(data.get("fecha_emision"), "%Y-%m-%d").date()
    except (ValueError, TypeError):
        issue_date = datetime.utcnow().date()
        
    # Account: a client's quotes always go to its own account; admin and ventas must pick one.
    opportunity = None
    if user.role == CLIENT:
        own = account_of_client_user(db, user)
        if own is None:
            # Without an account the quote would be saved but invisible to its own author.
            raise HTTPException(status_code=400, detail="Tu usuario todavía no está ligado a la cuenta de tu empresa. "
                                "Pedíselo a TOMATO para poder guardar cotizaciones.")
        account_id = own.id
    else:
        account_id = data.get("account_id")
        account = db.get(Account, account_id) if isinstance(account_id, int) else None
        if account is None or account.merged_into_id:
            raise HTTPException(status_code=400, detail="Elegí la cuenta del cliente (o creala) antes de guardar.")
        if data.get("opportunity_id"):
            opportunity = db.get(Opportunity, data.get("opportunity_id"))
            if opportunity is None or opportunity.account_id != account.id:
                raise HTTPException(status_code=400, detail="La oportunidad no es de esa cuenta.")

    # The quote being edited is identified by its id, never by its number: two people who
    # open the tool at once get the same proposed number, and the second save must not
    # replace the first one's quote. A new quote whose number is taken gets the next free one.
    quote = None
    renumbered_from = None
    if data.get("id") is not None:
        quote = visible_quotes(db, user).filter(Quote.id == data.get("id")).first()
        if quote is None:
            raise HTTPException(status_code=404, detail="La cotización ya no existe o no es tuya")
        taken = db.query(Quote.id).filter(Quote.numero_cotizacion == numero_cotizacion, Quote.id != quote.id).first()
        if taken:
            raise HTTPException(status_code=400, detail=f"El número {numero_cotizacion} ya lo usa otra cotización")
        quote.numero_cotizacion = numero_cotizacion
    elif db.query(Quote.id).filter(Quote.numero_cotizacion == numero_cotizacion).first():
        renumbered_from = numero_cotizacion
        numero_cotizacion = f"TCR-{issue_date.year}-{next_quote_sequence(db, issue_date.year):04d}"

    if quote:
        # Update
        quote.fecha_emision = issue_date
        quote.cliente_nombre = data.get("cliente_nombre")
        quote.cliente_datos = data.get("cliente_datos", {})
        quote.moneda = data.get("moneda", "CRC")
        quote.tipo_servicio = data.get("tipo_servicio")
        quote.frecuencia = data.get("frecuencia")
        quote.validez_dias = data.get("validez_dias", 15)
        quote.notes = data.get("notes")
        quote.terminos = data.get("terminos")
        quote.subtotal = data.get("subtotal", 0.0)
        quote.iva = data.get("iva", 0.0)
        quote.total = data.get("total", 0.0)
        quote.discount = number(data.get("discount"), 0.0)
        quote.tax_rate = number(data.get("tax_rate"), 13.0)
        quote.items = data.get("items", [])
    else:
        # Create
        quote = Quote(
            numero_cotizacion=numero_cotizacion,
            fecha_emision=issue_date,
            cliente_nombre=data.get("cliente_nombre"),
            cliente_datos=data.get("cliente_datos", {}),
            moneda=data.get("moneda", "CRC"),
            tipo_servicio=data.get("tipo_servicio"),
            frecuencia=data.get("frecuencia"),
            validez_dias=data.get("validez_dias", 15),
            notes=data.get("notes"),
            terminos=data.get("terminos"),
            subtotal=data.get("subtotal", 0.0),
            iva=data.get("iva", 0.0),
            total=data.get("total", 0.0),
            discount=number(data.get("discount"), 0.0),
            tax_rate=number(data.get("tax_rate"), 13.0),
            items=data.get("items", [])
        )
        db.add(quote)

    quote.account_id = account_id
    if user.role != CLIENT:
        quote.opportunity_id = opportunity.id if opportunity else None
    if opportunity is not None:
        advance_to_proposal(db, opportunity, user)
    db.commit()
    return {"status": "success", "id": quote.id, "numero_cotizacion": quote.numero_cotizacion,
            "renumbered_from": renumbered_from, "account_id": quote.account_id,
            "opportunity_id": quote.opportunity_id}



# --- Sending a quote by e-mail --------------------------------------------------------


MAX_RECIPIENTS = 5
EMAIL_RE = re.compile(r"^[^@\s,;]+@[^@\s,;]+\.[^@\s,;]+$")


def own_quote(db: Session, user: User, id: int) -> Quote:
    q = visible_quotes(db, user).filter(Quote.id == id).first()
    if not q:
        raise HTTPException(status_code=404, detail="Cotización no encontrada")
    return q


def make_pdf(q: Quote) -> bytes:
    try:
        return quote_pdf(q)
    except Exception as e:  # WeasyPrint missing or failing: say it instead of a blank error
        import logging
        logging.getLogger(__name__).error(f"PDF of {q.numero_cotizacion} failed: {e}")
        raise HTTPException(status_code=503, detail="No se pudo generar el PDF de la cotización. Avisale al admin.")


@router.get("/api/quotes/{id}/pdf")
def quote_pdf_file(id: int, db: Session = Depends(deps.get_db), user: User = Depends(deps.get_current_user)):
    """The PDF that the e-mail attaches (preview and download)."""
    check_quotes_access(user)
    q = own_quote(db, user, id)
    return Response(content=make_pdf(q), media_type="application/pdf",
                    headers={"Content-Disposition": f'inline; filename="{pdf_filename(q)}"'})


def history(db: Session, q: Quote):
    rows = db.query(QuoteEmail).filter(QuoteEmail.quote_id == q.id).order_by(QuoteEmail.sent_at.desc()).all()
    names = {u.id: (u.full_name or u.username) for u in db.query(User).filter(User.id.in_({r.sent_by_id for r in rows}))}
    return [{"sent_at": r.sent_at.isoformat() + "Z", "by": names.get(r.sent_by_id, ""), "to": r.recipients} for r in rows]


def sender_only(user: User):
    if not user.sells:
        raise HTTPException(status_code=403, detail="Solo el admin y ventas envían cotizaciones")


@router.get("/api/quotes/{id}/email")
def quote_email_form(id: int, db: Session = Depends(deps.get_db), user: User = Depends(deps.get_current_user)):
    """What the send window starts with, and the previous sends."""
    sender_only(user)
    q = own_quote(db, user, id)
    opportunity = db.get(Opportunity, q.opportunity_id) if q.opportunity_id else None
    data = default_email(q, user, today_cr(), account_contact_emails(db, q.account_id), hour=now_cr().hour)
    data.update(history=history(db, q), filename=pdf_filename(q), reply_to=user.email or "",
                opportunity={"id": opportunity.id, "title": opportunity.title,
                             "open": opportunity.stage not in CLOSED_STAGES} if opportunity else None)
    return data


def account_contact_emails(db: Session, account_id) -> list:
    """The account's main contact with an e-mail (primary first, then commercial ones)."""
    from app.db.models.crm import Contact
    if not account_id:
        return []
    contacts = db.query(Contact).filter(Contact.account_id == account_id, Contact.email.isnot(None), Contact.email != "")
    ranked = sorted(contacts, key=lambda c: (not c.is_primary, not c.is_commercial, c.id))
    return [ranked[0].email] if ranked else []


def recipients_of(value) -> list:
    items = value if isinstance(value, list) else re.split(r"[,;\s]+", str(value or ""))
    emails = []
    for item in items:
        email = str(item).strip().lower()
        if email and email not in emails:
            emails.append(email)
    return emails


@router.post("/api/quotes/{id}/email")
async def send_quote(id: int, request: Request, db: Session = Depends(deps.get_db),
                     user: User = Depends(deps.get_current_user)):
    """Sends the quote's PDF from the notifications account; replies go to the person who sends.
    Records the send in the quote and in Clientes (follow-up, Propuesta stage, next step)."""
    sender_only(user)
    q = own_quote(db, user, id)
    data = await request.json()
    to = recipients_of(data.get("to"))
    wrong = [e for e in to if not EMAIL_RE.match(e)]
    if not to:
        raise HTTPException(status_code=400, detail="Escribí al menos un correo")
    if wrong:
        raise HTTPException(status_code=400, detail=f"Revisá este correo: {wrong[0]}")
    if len(to) > MAX_RECIPIENTS:
        raise HTTPException(status_code=400, detail=f"Máximo {MAX_RECIPIENTS} destinatarios por envío")
    subject = (data.get("subject") or "").strip()[:200] or f"Cotización {q.numero_cotizacion} · TOMATO"
    message = (data.get("message") or "").strip()
    if not message:
        raise HTTPException(status_code=400, detail="Escribí el mensaje del correo")
    next_step_date = None
    if data.get("next_step_date"):
        try:
            next_step_date = date.fromisoformat(str(data.get("next_step_date")))
        except ValueError:
            raise HTTPException(status_code=400, detail="La fecha del próximo paso no es válida")

    pdf = make_pdf(q)
    opportunity = db.get(Opportunity, q.opportunity_id) if q.opportunity_id else None
    owner = db.get(User, opportunity.owner_id) if opportunity and opportunity.owner_id else None
    reply_to = [user.email or (owner.email if owner else None)]
    if not await send_quote_email(to, subject, message, pdf, pdf_filename(q), reply_to):
        raise HTTPException(status_code=502, detail="No se pudo enviar el correo. Intentá de nuevo en un momento.")

    from datetime import datetime
    from app.db.models.crm import CrmActivity
    now = datetime.utcnow()
    db.add(QuoteEmail(quote_id=q.id, sent_at=now, sent_by_id=user.id, recipients=", ".join(to), subject=subject,
                      message=message))
    if q.account_id:
        db.add(CrmActivity(account_id=q.account_id, opportunity_id=q.opportunity_id, type="correo", happened_at=now,
                           user_id=user.id, notes=f"Cotización {q.numero_cotizacion} enviada por correo a {', '.join(to)}"))
    if opportunity is not None and opportunity.stage not in CLOSED_STAGES:
        advance_to_proposal(db, opportunity, user)
        if next_step_date:
            opportunity.next_step = f"Dar seguimiento a la cotización {q.numero_cotizacion}"
            opportunity.next_step_date = next_step_date
    db.commit()
    log_activity(db, user=user, action="UPDATE", entity_type="QUOTE", entity_id=q.id,
                 details=f"Envió la cotización {q.numero_cotizacion} a {', '.join(to)}")
    return {"ok": True, "message": f"Cotización enviada a {', '.join(to)}", "history": history(db, q)}
