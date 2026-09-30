"""The quote's PDF made by the server (to attach it to an e-mail), with the same content and
look as the one the quote tool prints (app/static/cotizador/app.js, buildPrintableHTML), and the
defaults of the e-mail that sends it."""
from datetime import date, timedelta
from pathlib import Path
from typing import Dict, List, Optional

from app.core.templates import templates
from app.db.models.quote import Quote
from app.db.models.user import User

STATIC = Path(__file__).resolve().parent.parent / "static"

# Same issuer data as the quote tool.
ISSUER = {"name": "TOMATO COSTA RICA ANY S.R.L.", "tax_id": "3-102-876296", "address": "Alajuela, Costa Rica",
          "phone": "+506 7080 8613", "web": "www.tomatocr.com"}


def money(value, currency: str) -> str:
    """Like the browser in the quote tool: ₡1 234 567,89 (es-CR) and $1,234,567.89 (en-US)."""
    amount = float(value or 0)
    if (currency or "CRC").upper() == "USD":
        return f"{'-' if amount < 0 else ''}${abs(amount):,.2f}"
    text = f"{abs(amount):,.2f}".replace(",", " ").replace(".", ",")
    return f"{'-' if amount < 0 else ''}₡{text}"


def totals(quote: Quote) -> Dict:
    """The same math as totalsOf() in the quote tool."""
    items = quote.items or []
    subtotal = sum(float(it.get("qty") or 0) * float(it.get("unitPrice") or 0) for it in items)
    discount = max(0.0, float(quote.discount or 0))
    base = max(0.0, subtotal - discount)
    rate = float(quote.tax_rate if quote.tax_rate is not None else 13)
    # Same rule as quoteFromData(): IVA 0 only means "no IVA" when there was something to tax.
    tax_enabled = (quote.iva or 0) > 0 or not (base > 0 and rate > 0)
    tax = base * rate / 100 if tax_enabled else 0.0
    return {"subtotal": subtotal, "discount": discount, "tax": tax, "total": base + tax,
            "tax_enabled": tax_enabled, "tax_rate": rate}


def valid_until(quote: Quote) -> Optional[date]:
    if not quote.fecha_emision:
        return None
    return quote.fecha_emision + timedelta(days=int(quote.validez_dias or 0))


def text_lines(text: Optional[str]) -> List[str]:
    return [line.rstrip() for line in str(text or "").strip().split("\n")] if (text or "").strip() else []


def quote_html(quote: Quote) -> str:
    client = quote.cliente_datos or {}
    client_rows = [(label, str(client.get(key) or "").strip()) for label, key in
                   (("Cliente", "name"), ("Contacto", "id"), ("Correo", "email"), ("Teléfono", "phone"),
                    ("Ubicación", "address"))]
    currency = (quote.moneda or "CRC").upper()
    return templates.get_template("quotes/pdf.html").render(
        q=quote, issuer=ISSUER, client_rows=[r for r in client_rows if r[1]], totals=totals(quote),
        valid_until=valid_until(quote), money=lambda v: money(v, currency), currency=currency,
        notes=text_lines(quote.notes), terms=text_lines(quote.terminos), logo=(STATIC / "cotizador" / "LogoTomatoB.png").as_uri())


def quote_pdf(quote: Quote) -> bytes:
    """The PDF, with WeasyPrint (the server needs Pango: see README, "Cotizaciones por correo")."""
    from weasyprint import HTML  # imported here: the rest of the app works without it
    return HTML(string=quote_html(quote), base_url=str(STATIC)).write_pdf()


def pdf_filename(quote: Quote) -> str:
    return f"{quote.numero_cotizacion}.pdf"


# --- The e-mail -------------------------------------------------------------------

def business_days_after(start: date, days: int) -> date:
    current = start
    while days > 0:
        current += timedelta(days=1)
        if current.weekday() < 5:
            days -= 1
    return current


def greeting(now_cr_hour: int) -> str:
    return "Buenos días" if now_cr_hour < 12 else "Buenas tardes"


FOLLOW_UP_BUSINESS_DAYS = 3


def default_email(quote: Quote, user: User, today: date, fallback_to: Optional[List[str]] = None,
                  hour: int = 9) -> Dict:
    """What the send window shows before the person edits it. No amount: the client opens the
    PDF. The TOMATO signature (with the logo) is added when sending, not here. Without an
    e-mail in the quote, `fallback_to` (the account's main contact)."""
    client = quote.cliente_datos or {}
    contact = str(client.get("id") or "").strip()  # the contact's name (the client's name is a company)
    first_name = contact.split()[0] if contact else ""
    service = (quote.tipo_servicio or "").strip()
    until = valid_until(quote)
    lines = [
        f"{greeting(hour)}{', ' + first_name if first_name else ''}:",
        "",
        f"Adjuntamos la cotización {quote.numero_cotizacion}"
        + (f" del servicio de {service.lower()} que nos solicitó." if service else " que nos solicitó.")
        + (f" La propuesta es válida hasta el {until:%d/%m/%Y}." if until else ""),
        "",
        "Estaremos a la espera de sus comentarios; como parte de nuestro proceso, le daremos seguimiento "
        f"en {FOLLOW_UP_BUSINESS_DAYS} días hábiles.",
        "",
        "Quedamos atentos a cualquier consulta, ajuste o solicitud adicional.",
        "",
        "Saludos cordiales,",
    ]
    email = str(client.get("email") or "").strip()
    return {"to": [email] if email else list(fallback_to or []),
            "subject": f"Cotización {quote.numero_cotizacion} · TOMATO",
            "message": "\n".join(lines),
            "next_step_date": business_days_after(today, FOLLOW_UP_BUSINESS_DAYS).isoformat()}
