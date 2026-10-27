"""Notifications (app/db/models/notification.py): notify() adds one to the bell and, when the
person wants it and has an e-mail, to the outbox. deliver() sends the outbox: right after the
request (send_soon) and every few minutes from scripts/notificaciones.py, which also retries
failures, sends the daily digest and deletes old ones.

At night (QUIET_FROM to QUIET_UNTIL, Costa Rica) only urgent ones are e-mailed; the rest wait
for the morning run."""
import logging
from datetime import date, datetime, timedelta
from typing import Iterable, List, Optional, Tuple

from fastapi import BackgroundTasks
from sqlalchemy.orm import Session

from app.core.roles import CLIENT
from app.db.models.notification import DIGEST, KINDS, DigestSent, Notification, NotificationPref
from app.db.models.user import User
from app.db.session import SessionLocal
from app.utils.email import send_plain_email
from app.utils.timecr import now_cr

logger = logging.getLogger(__name__)

SITE = "https://tomatocr.com"
MAX_ATTEMPTS = 5
QUIET_FROM, QUIET_UNTIL = 21, 6
# The digest goes from this hour; after LAST_DIGEST_HOUR it's too late to be "the day's".
DIGEST_HOUR, LAST_DIGEST_HOUR = 7, 12
# A run that died while sending leaves it "sending"; after this it goes back to the outbox.
STUCK_AFTER = timedelta(minutes=15)
KEEP_READ_DAYS = 90


# --- Preferences ------------------------------------------------------------------

def wants_email(db: Session, user: User, kind: str) -> bool:
    pref = db.query(NotificationPref).filter(NotificationPref.user_id == user.id, NotificationPref.kind == kind).first()
    if pref is not None:
        return pref.email
    return KINDS[kind][1] if kind in KINDS else True


def set_pref(db: Session, user: User, kind: str, email: bool):
    pref = db.query(NotificationPref).filter(NotificationPref.user_id == user.id, NotificationPref.kind == kind).first() \
        or NotificationPref(user_id=user.id, kind=kind)
    pref.email = email
    db.add(pref)


# --- Adding them ------------------------------------------------------------------

def notify(db: Session, user: User, kind: str, title: str, body: Optional[str] = None,
           link: Optional[str] = None, urgent: bool = False) -> Notification:
    """Adds a notification for this person (the caller commits, then calls send_soon)."""
    by_email = bool(user.email) and wants_email(db, user, kind)
    notification = Notification(user_id=user.id, kind=kind, title=title[:200], body=body, link=link, urgent=urgent,
                                email_status="pending" if by_email else "none")
    db.add(notification)
    return notification


def send_soon(background: BackgroundTasks, notifications: Iterable[Notification]):
    """After the commit: send their e-mails once the response is out."""
    ids = [n.id for n in notifications if n.email_status == "pending"]
    if ids:
        background.add_task(deliver, ids)


def unread_count(db: Session, user: User) -> int:
    return db.query(Notification).filter(Notification.user_id == user.id, Notification.read_at.is_(None)).count()


# --- Sending the outbox -----------------------------------------------------------

def quiet(now: datetime) -> bool:
    return now.hour >= QUIET_FROM or now.hour < QUIET_UNTIL


def email_body(notification: Notification) -> str:
    lines = [notification.body] if notification.body else []
    if notification.link:
        lines += ["", f"Ver en el sistema: {SITE}{notification.link}"]
    lines += ["", f"Para elegir qué avisos te llegan por correo: {SITE}/notificaciones"]
    return "\n".join(lines).strip()


async def deliver(ids: Optional[List[int]] = None) -> int:
    """Sends the outbox (only these ids, if given). Each one is taken with a conditional update,
    so two processes never send the same. Returns how many went out."""
    db = SessionLocal()
    sent = 0
    try:
        query = db.query(Notification.id).filter(Notification.email_status == "pending")
        if ids is not None:
            query = query.filter(Notification.id.in_(ids))
        if quiet(now_cr()):
            query = query.filter(Notification.urgent == True)  # noqa: E712
        for (notification_id,) in query.order_by(Notification.id).all():
            taken = db.query(Notification).filter(Notification.id == notification_id,
                                                  Notification.email_status == "pending").update(
                {"email_status": "sending", "emailed_at": datetime.utcnow()}, synchronize_session=False)
            db.commit()
            if not taken:
                continue
            notification = db.get(Notification, notification_id)
            db.refresh(notification)
            if not notification.user.email:
                notification.email_status = "none"
                db.commit()
                continue
            ok = await send_plain_email([notification.user.email], notification.title, email_body(notification))
            notification.email_attempts += 1
            if ok:
                notification.email_status, notification.emailed_at = "sent", datetime.utcnow()
                sent += 1
            else:
                notification.email_status = "failed" if notification.email_attempts >= MAX_ATTEMPTS else "pending"
            db.commit()
    finally:
        db.close()
    return sent


def release_stuck(db: Session) -> int:
    count = db.query(Notification).filter(Notification.email_status == "sending",
                                          Notification.emailed_at < datetime.utcnow() - STUCK_AFTER).update(
        {"email_status": "pending"}, synchronize_session=False)
    db.commit()
    return count


# --- Daily digest -----------------------------------------------------------------

def digest_email(db: Session, user: User, today: date) -> Optional[Tuple[str, str]]:
    """Subject and body with the person's tasks for today (and late ones) and their urgent
    alerts; None when there is nothing."""
    from app.routers.dashboard import current_alerts  # the Dashboard's own alerts, computed the same way
    from app.utils.tasks import my_tasks

    tasks = my_tasks(db, user, today)["today"]
    urgent = [a for a in current_alerts(db, user) if a.level == "urgente"]
    if not tasks and not urgent:
        return None
    lines = []
    if tasks:
        lines.append(f"Tareas de hoy y atrasadas ({len(tasks)}):")
        for task in tasks:
            late = " (atrasada)" if task.due_date < today else ""
            high = " [Alta]" if task.priority == "alta" else ""
            lines.append(f"- {task.title}{high}{late}")
        lines.append("")
    if urgent:
        lines.append("Urgente:")
        lines += [f"- {a.title}: {a.detail}" for a in urgent]
        lines.append("")
    lines += [f"Ver en el sistema: {SITE}/dashboard/", "",
              f"Para dejar de recibir este resumen: {SITE}/notificaciones"]
    parts = [f"{len(tasks)} tarea{'s' if len(tasks) != 1 else ''}"] if tasks else []
    if urgent:
        parts.append(f"{len(urgent)} urgente{'s' if len(urgent) != 1 else ''}")
    return f"Tu día en TOMATO: {', '.join(parts)}", "\n".join(lines)


async def send_digests(db: Session, now: datetime) -> int:
    """The day's digest to each active team member with an e-mail who wants it, once a day."""
    if not DIGEST_HOUR <= now.hour < LAST_DIGEST_HOUR:
        return 0
    today = now.date()
    done = {d.user_id for d in db.query(DigestSent).filter(DigestSent.day == today)}
    people = db.query(User).filter(User.is_active != False, User.role != CLIENT,  # noqa: E712
                                   User.email.isnot(None), User.email != "").order_by(User.id).all()
    sent = 0
    for person in people:
        if person.id in done or person.status in ("inactive", "liquidated") or not wants_email(db, person, DIGEST):
            continue
        mail = digest_email(db, person, today)
        if mail is not None and not await send_plain_email([person.email], *mail):
            continue  # the next run tries again
        db.add(DigestSent(user_id=person.id, day=today))
        db.commit()
        sent += mail is not None
    return sent


# --- The periodic run -------------------------------------------------------------

def clean_up(db: Session, today: date):
    db.query(Notification).filter(Notification.read_at < datetime.utcnow() - timedelta(days=KEEP_READ_DAYS)).delete(
        synchronize_session=False)
    db.query(DigestSent).filter(DigestSent.day < today - timedelta(days=30)).delete(synchronize_session=False)
    db.commit()


async def run_once() -> dict:
    """What scripts/notificaciones.py does every few minutes."""
    db = SessionLocal()
    try:
        now = now_cr()
        released = release_stuck(db)
        sent = await deliver()
        digests = await send_digests(db, now)
        clean_up(db, now.date())
        return {"released": released, "sent": sent, "digests": digests}
    finally:
        db.close()
