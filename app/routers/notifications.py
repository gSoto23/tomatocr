"""Notificaciones (/notificaciones): the bell's list and what each person wants by e-mail.
For the team; the client has none. app/utils/notifications.py."""
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session, object_session

from app.core.roles import CLIENT
from app.core.templates import templates
from app.db.models.notification import DIGEST, DIGEST_LABEL, KINDS, Notification
from app.db.models.user import User
from app.routers import deps
from app.routers.crm import toast_redirect
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
    return templates.TemplateResponse("notifications/index.html", {
        "request": request, "user": user, "notifications": notifications, "prefs": prefs,
        "unread": sum(1 for n in notifications if n.read_at is None)})


@router.post("/{notification_id}/abrir")
def open_one(notification_id: int, db: Session = Depends(deps.get_db), user: User = Depends(team_user)):
    """Marks it read and goes where it points."""
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
