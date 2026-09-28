import os
import re
from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.core.templates import templates
from app.db.models.crm import Account, Opportunity
from app.db.models.user import User
from app.db.models.quote import Quote
from app.routers import deps
from app.core.roles import CLIENT, QUOTES_ROLES
from app.utils.crm import account_of_client_user, advance_to_proposal

router = APIRouter(
    tags=["quotes"],
    dependencies=[Depends(deps.require_roles(*QUOTES_ROLES))]
)

def check_quotes_access(user: User):
    # El "Cotizador" solo se muestra en la UI a admin, client y ventas
    # (ver base_dashboard.html) — replicamos esa misma regla acá.
    if user.role not in QUOTES_ROLES:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized")


def visible_quotes(db: Session, user: User):
    """Admin and ventas see every quote; a client only the quotes of its own account."""
    query = db.query(Quote)
    if user.role == CLIENT:
        account = account_of_client_user(db, user)
        query = query.filter(Quote.account_id == (account.id if account else -1))
    return query


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
    }


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

@router.get("/api/quotes/{id}")
def get_quote(id: int, db: Session = Depends(deps.get_db), user: User = Depends(deps.get_current_user)):
    check_quotes_access(user)
    q = visible_quotes(db, user).filter(Quote.id == id).first()
    if not q:
        raise HTTPException(status_code=404, detail="Cotización no encontrada")
    return serialize(q, account_names(db, [q]))

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
        account_id = own.id if own else None
    else:
        account_id = data.get("account_id")
        account = db.get(Account, account_id) if isinstance(account_id, int) else None
        if account is None or account.merged_into_id:
            raise HTTPException(status_code=400, detail="Elija la cuenta del cliente (o créela) antes de guardar.")
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
