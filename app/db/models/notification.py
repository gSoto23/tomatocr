"""Notifications: what the bell shows and what goes out by e-mail (app/utils/notifications.py).
Each one is for one person; the e-mail goes from an outbox so a failure is retried."""
from datetime import datetime

from sqlalchemy import Boolean, Column, Date, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import relationship

from app.db.base_class import Base

# Kind: (name in Preferences, e-mail on by default).
KINDS = {
    "task_assigned": ("Te asignan una tarea", True),
    "task_high": ("Una tarea tuya pasa a prioridad alta", True),
    "task_done": ("Terminan una tarea que asignaste", False),
    "opportunity_assigned": ("Te asignan una oportunidad", True),
    "new_lead": ("Entra un prospecto nuevo tuyo", True),
}
# Not a notification of its own: the 7 a.m. e-mail with the day's tasks and urgent alerts.
DIGEST = "daily_digest"
DIGEST_LABEL = "Resumen del día por correo (7 a.m.)"

# E-mail of a notification: pending (in the outbox), sending (one process took it), sent,
# failed (gave up after MAX_ATTEMPTS) or none (not wanted, or the person has no e-mail).
EMAIL_STATUSES = ("pending", "sending", "sent", "failed", "none")


class Notification(Base):
    __tablename__ = "notifications"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    kind = Column(String(30), nullable=False)
    title = Column(String(200), nullable=False)
    body = Column(Text, nullable=True)
    link = Column(String(300), nullable=True)
    # Urgent ones are e-mailed at night too; the rest wait until the morning.
    urgent = Column(Boolean, nullable=False, default=False, server_default="false")
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    read_at = Column(DateTime, nullable=True)
    email_status = Column(String(10), nullable=False, default="none", server_default="none", index=True)
    email_attempts = Column(Integer, nullable=False, default=0, server_default="0")
    # When it was taken for sending, then when it was sent.
    emailed_at = Column(DateTime, nullable=True)

    user = relationship("User")


class NotificationPref(Base):
    """A person's choice for one kind (or the digest). No row: the kind's default."""
    __tablename__ = "notification_prefs"
    __table_args__ = (UniqueConstraint("user_id", "kind", name="uq_notification_pref"),)

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    kind = Column(String(30), nullable=False)
    email = Column(Boolean, nullable=False)


class DigestSent(Base):
    """The daily digest went to this person on this day (Costa Rica), so it goes once."""
    __tablename__ = "notification_digests"
    __table_args__ = (UniqueConstraint("user_id", "day", name="uq_notification_digest"),)

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    day = Column(Date, nullable=False)
