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
from app.utils import push
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
