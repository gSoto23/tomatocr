"""Notificaciones (/notificaciones): the bell's list, what each person wants by e-mail, and
the phones where they turned notifications on (web push, app/utils/push.py). For the team;
the client has none. app/utils/notifications.py."""
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session, object_session

from app.core.roles import CLIENT
from app.core.templates import templates
from app.core.config import settings
from app.db.models.notification import DIGEST, DIGEST_LABEL, KINDS, Notification, PushSubscription
from app.db.models.user import User
from app.routers import deps
from app.routers.crm import toast_redirect
from app.utils import notice_format, push
from app.utils.notifications import set_pref, unread_count, wants_email

router = APIRouter(prefix="/notificaciones", tags=["notificaciones"])
SHOWN = 50


def team_user(user: User = Depends(deps.get_current_user)) -> User:
    if user.role == CLIENT:
        raise HTTPException(status_code=403, detail="Las notificaciones son para el equipo")
    return user


def bell_count(user) -> int:
    """Unread notifications for the bell in the header (0 for the client or without a session)."""
    db = object_session(user) if user is not None else None
    if db is None or getattr(user, "role", CLIENT) == CLIENT:
        return 0
    return unread_count(db, user)


templates.env.globals["bell_count"] = bell_count
templates.env.globals["notice_style"] = notice_format.style
templates.env.globals["notice_heading"] = notice_format.heading
templates.env.globals["notice_summary"] = notice_format.summary
# Tailwind classes per color of notice_format.KIND_STYLE, and an icon (SVG path) per kind.
templates.env.globals["notice_classes"] = {
    "blue": "bg-blue-100 text-blue-700", "red": "bg-red-100 text-red-700", "green": "bg-green-100 text-green-700",
    "purple": "bg-purple-100 text-purple-700", "amber": "bg-amber-100 text-amber-700", "black": "bg-gray-900 text-white",
}
templates.env.globals["notice_icons"] = {
    "task_assigned": "M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2m-6 9l2 2 4-4",
    "task_high": "M12 9v2m0 4h.01M5.07 19h13.86c1.54 0 2.5-1.67 1.73-3L13.73 4c-.77-1.33-2.69-1.33-3.46 0L3.34 16c-.77 1.33.19 3 1.73 3z",
    "task_done": "M5 13l4 4L19 7",
    "opportunity_assigned": "M13 7h8m0 0v8m0-8l-8 8-4-4-6 6",
    "new_lead": "M18 9v3m0 0v3m0-3h3m-3 0h-3m-2-5a4 4 0 11-8 0 4 4 0 018 0zM3 20a6 6 0 0112 0v1H3v-1z",
    "daily_digest": "M8 7V3m8 4V3m-9 8h10M5 21h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z",
    "default": "M15 17h5l-1.405-1.405A2.032 2.032 0 0118 14.158V11a6.002 6.002 0 00-4-5.659V5a2 2 0 10-4 0v.341C7.67 6.165 6 8.388 6 11v3.159c0 .538-.214 1.055-.595 1.436L4 17h5m6 0v1a3 3 0 11-6 0v-1m6 0H9",
}


@router.get("")
def index(request: Request, db: Session = Depends(deps.get_db), user: User = Depends(team_user)):
    notifications = db.query(Notification).filter(Notification.user_id == user.id).order_by(
        Notification.created_at.desc(), Notification.id.desc()).limit(SHOWN).all()
    prefs = [(kind, label, wants_email(db, user, kind)) for kind, (label, _) in KINDS.items()]
    prefs.append((DIGEST, DIGEST_LABEL, wants_email(db, user, DIGEST)))
    devices = db.query(PushSubscription).filter(PushSubscription.user_id == user.id).count()
    return templates.TemplateResponse("notifications/index.html", {
        "request": request, "user": user, "notifications": notifications, "prefs": prefs,
        "unread": sum(1 for n in notifications if n.read_at is None),
        "push_key": settings.VAPID_PUBLIC_KEY if push.configured() else "", "devices": devices})


# --- This phone (web push) --------------------------------------------------------
# Called by the page's script with the browser's subscription (JSON). Declared before the
# /{notification_id}/... routes so "push" is never read as an id.

@router.post("/push")
async def turn_on(request: Request, db: Session = Depends(deps.get_db), user: User = Depends(team_user)):
    if not push.configured():
        raise HTTPException(status_code=503, detail="Los avisos al celular no están configurados")
    data = await request.json()
    keys = data.get("keys") or {}
    endpoint, p256dh, auth = data.get("endpoint"), keys.get("p256dh"), keys.get("auth")
    if not (isinstance(endpoint, str) and endpoint.startswith("https://") and p256dh and auth):
        raise HTTPException(status_code=400, detail="Suscripción inválida")
    push.save_device(db, user.id, endpoint, str(p256dh)[:200], str(auth)[:100], request.headers.get("user-agent"))
    db.commit()
    return {"ok": True}


@router.post("/push/quitar")
async def turn_off(request: Request, db: Session = Depends(deps.get_db), user: User = Depends(team_user)):
    endpoint = (await request.json()).get("endpoint")
    db.query(PushSubscription).filter(PushSubscription.user_id == user.id,
                                      PushSubscription.endpoint == endpoint).delete(synchronize_session=False)
    db.commit()
    return {"ok": True}


@router.post("/push/prueba")
async def test_push(db: Session = Depends(deps.get_db), user: User = Depends(team_user)):
    """A test notification to every device of this person, right now (no bell, no outbox)."""
    ok = await push.push_to(db, user.id, {"title": "TOMATO: prueba", "body": "Así te van a llegar los avisos.",
                                          "url": "/notificaciones", "tag": "prueba"})
    return {"ok": bool(ok)}


@router.post("/{notification_id}/abrir")
def open_one(notification_id: int, db: Session = Depends(deps.get_db), user: User = Depends(team_user)):
    """Marks it read and goes where it points."""
    return _open(db, notification_id, user)


@router.get("/{notification_id}/ir")
def open_from_phone(notification_id: int, db: Session = Depends(deps.get_db), user: User = Depends(team_user)):
    """Same, from a phone notification (a link, so a GET)."""
    return _open(db, notification_id, user)


def _open(db: Session, notification_id: int, user: User) -> RedirectResponse:
    notification = db.get(Notification, notification_id)
    if notification is None or notification.user_id != user.id:
        raise HTTPException(status_code=404, detail="Notificación no encontrada")
    notification.read_at = notification.read_at or datetime.utcnow()
    db.commit()
    return RedirectResponse(url=notification.link or "/notificaciones", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/leidas")
def read_all(db: Session = Depends(deps.get_db), user: User = Depends(team_user)):
    db.query(Notification).filter(Notification.user_id == user.id, Notification.read_at.is_(None)).update(
        {"read_at": datetime.utcnow()}, synchronize_session=False)
    db.commit()
    return toast_redirect("/notificaciones", "Todas marcadas como leídas")


@router.post("/preferencias")
async def save_prefs(request: Request, db: Session = Depends(deps.get_db), user: User = Depends(team_user)):
    """One checkbox per kind (and the digest): ticked, it also goes by e-mail."""
    form = await request.form()
    for kind in list(KINDS) + [DIGEST]:
        set_pref(db, user, kind, form.get(f"email_{kind}") is not None)
    db.commit()
    message = "Preferencias guardadas" if user.email else \
        "Preferencias guardadas. No tenés correo en tu usuario: pedile al admin que lo agregue"
    return toast_redirect("/notificaciones", message, error=not user.email)
