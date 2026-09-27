"""Public lead entry points: contact form, thank-you page, privacy policy, and the
server-to-server API used by darboles.com. docs/DISENO_CRM.md, section 6."""
import hmac
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.templates import templates
from app.db.models.crm import LABELS, MOTORS
from app.db.models.user import User
from app.routers import deps
from app.utils.email import send_plain_email
from app.utils.leads import (CONSENT_TEXT_VERSION, LeadRejected, clean_lead, intake_lead, notification,
                             rate_limited, record_submission)

router = APIRouter(tags=["leads"])

TOO_MANY = "Recibimos muchas solicitudes en poco tiempo. Intentá de nuevo en una hora o escribinos por WhatsApp."


def notify(background: BackgroundTasks, db: Session, result, lead, source):
    owner = db.get(User, result.opportunity.owner_id) if result.opportunity.owner_id else None
    message = notification(result, lead, source)
    background.add_task(send_plain_email, [owner.email if owner else None, settings.LEADS_NOTIFY_EMAIL],
                        message["subject"], message["body"])


@router.api_route("/privacidad", methods=["GET", "HEAD"])
def privacy(request: Request):
    return templates.TemplateResponse("privacidad.html", {"request": request, "version": CONSENT_TEXT_VERSION})


@router.api_route("/contacto/gracias", methods=["GET", "HEAD"])
def thanks(request: Request):
    return templates.TemplateResponse("contacto_gracias.html", {"request": request})


@router.post("/contacto")
async def contact(request: Request, background: BackgroundTasks, db: Session = Depends(deps.get_db)):
    """The public form. Answers JSON to the page's script, or redirects when sent without JavaScript."""
    wants_json = "application/json" in request.headers.get("accept", "")
    try:
        data = await request.json() if "application/json" in request.headers.get("content-type", "") \
            else dict(await request.form())
    except ValueError:
        data = {}
    if not isinstance(data, dict):
        data = {}

    def answer(ok: bool, message: str, status: int = 200):
        if wants_json:
            return JSONResponse(status_code=status, content={"ok": ok, "message": message})
        if ok:
            return RedirectResponse(url="/contacto/gracias", status_code=303)
        return templates.TemplateResponse("contacto_gracias.html", {"request": request, "error": message},
                                          status_code=status)

    # Honeypot: people never see this field; bots fill it. Pretend it worked.
    if str(data.get("website") or "").strip():
        return answer(True, "¡Gracias! Te contactamos pronto.")

    ip = request.client.host if request.client else None
    if rate_limited(db, "web", ip, settings.LEADS_PER_IP_PER_HOUR, settings.LEADS_PER_HOUR):
        return answer(False, TOO_MANY, 429)
    try:
        lead = clean_lead(data)
    except LeadRejected as e:
        return answer(False, ". ".join(e.errors) + ".", 400)
    record_submission(db, "web", ip)
    result = intake_lead(db, lead, "web")
    notify(background, db, result, lead, "web")
    return answer(True, "¡Gracias! Recibimos tu solicitud y te contactamos pronto.")


@router.post("/api/crm/leads")
async def darboles_lead(request: Request, background: BackgroundTasks, db: Session = Depends(deps.get_db),
                        x_api_key: Optional[str] = Header(None)):
    """darboles.com sends leads from its own server with the key in the X-API-Key header.
    No CORS: browsers of other sites can't call it, only a server that holds the key."""
    if not settings.DARBOLES_API_KEY:
        raise HTTPException(status_code=503, detail="API de prospectos no configurada")
    if not x_api_key or not hmac.compare_digest(x_api_key, settings.DARBOLES_API_KEY):
        raise HTTPException(status_code=401, detail="Clave inválida")
    if rate_limited(db, "darboles", None, 0, 120):
        raise HTTPException(status_code=429, detail="Demasiadas solicitudes; intente más tarde")
    try:
        lead = clean_lead(await request.json())
    except LeadRejected as e:
        raise HTTPException(status_code=422, detail=e.errors)
    except ValueError:
        raise HTTPException(status_code=400, detail="El cuerpo debe ser JSON")
    record_submission(db, "darboles", None)
    result = intake_lead(db, lead, "darboles")
    notify(background, db, result, lead, "darboles")
    return {"ok": True, "account_id": result.account.id, "opportunity_id": result.opportunity.id,
            "new_account": result.new_account, "new_opportunity": result.new_opportunity}


def contact_form_context(default_motor: Optional[str] = None):
    """Options for the form partial (templates/components/contact_form.html)."""
    return {"motors": [(m, LABELS["motor"][m]) for m in MOTORS], "default_motor": default_motor}


templates.env.globals["contact_form_context"] = contact_form_context
