from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, status, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.core.templates import templates
from app.db.session import SessionLocal
from app.db.models.user import User
from app.db.models.quote import Quote
from app.routers import deps

router = APIRouter(
    tags=["quotes"],
    dependencies=[Depends(deps.get_current_user)]
)

@router.get("/cotizador", response_class=JSONResponse)
async def view_cotizador(request: Request, user: User = Depends(deps.get_current_user)):
    # Render the template
    return templates.TemplateResponse("cotizador/index.html", {"request": request, "user": user})

@router.get("/api/quotes/next-number")
async def get_next_quote_number(db: Session = Depends(deps.get_db)):
    count = db.query(Quote).count()
    return {"next_number": count + 1}

@router.get("/api/quotes/")
async def list_quotes(
    db: Session = Depends(deps.get_db), 
    limit: int = 20
):
    quotes = db.query(Quote).order_by(Quote.created_at.desc()).limit(limit).all()
    
    # We serialize it to match what the frontend expects
    return [
        {
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
            "items": q.items
        } for q in quotes
    ]

@router.get("/api/quotes/{id}")
async def get_quote(id: int, db: Session = Depends(deps.get_db)):
    q = db.query(Quote).filter(Quote.id == id).first()
    if not q:
        raise HTTPException(status_code=404, detail="Cotización no encontrada")
    
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
        "items": q.items
    }

@router.post("/api/quotes/")
async def upsert_quote(request: Request, db: Session = Depends(deps.get_db), user: User = Depends(deps.get_current_user)):
    data = await request.json()
    numero_cotizacion = data.get("numero_cotizacion")
    
    if not numero_cotizacion:
        raise HTTPException(status_code=400, detail="numero_cotizacion es requerido")
        
    from datetime import datetime
    try:
        issue_date = datetime.strptime(data.get("fecha_emision"), "%Y-%m-%d").date()
    except (ValueError, TypeError):
        issue_date = datetime.utcnow().date()
        
    quote = db.query(Quote).filter(Quote.numero_cotizacion == numero_cotizacion).first()
    
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
            items=data.get("items", [])
        )
        db.add(quote)
        
    db.commit()
    return {"status": "success", "id": quote.id}
