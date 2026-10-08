"""Login rate limiting: 5 failures within 15 minutes lock a username or an IP
for 15 minutes. Attempts are stored in the database, so the limit holds across
all gunicorn workers.
"""
import ipaddress
import logging
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.db.models.activity import ActivityLog
from app.db.models.login_attempt import LoginAttempt
from app.db.models.user import User

logger = logging.getLogger(__name__)

MAX_FAILURES = 5  # per account
# Per IP: much higher, because a whole office shares one public IP and one person's typos
# must not lock everyone out (the real IP is seen since nginx passes it on).
MAX_IP_FAILURES = 20
WINDOW = timedelta(minutes=15)


def trackable_ip(ip: Optional[str]) -> Optional[str]:
    """Returns the IP only if it identifies a real client.

    Behind a proxy every request may arrive from a loopback or private
    address; counting those would let a few failures lock out everyone.
    """
    if not ip:
        return None
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return None
    if addr.is_loopback or addr.is_private or addr.is_link_local or addr.is_unspecified:
        return None
    return ip


def client_ip(request) -> Optional[str]:
    """The visitor's IP. Behind nginx (on this same server) every request comes from
    127.0.0.1, so then the IP nginx passes on is used: X-Real-IP, or the last entry of
    X-Forwarded-For (the one nginx adds; earlier entries can be typed by anyone). From any
    other address those headers are ignored: they could be faked."""
    peer = request.client.host if request.client else None
    try:
        from_proxy = peer is not None and ipaddress.ip_address(peer).is_loopback
    except ValueError:
        from_proxy = False
    if from_proxy:
        real = (request.headers.get("x-real-ip") or "").strip()
        forwarded = [part.strip() for part in (request.headers.get("x-forwarded-for") or "").split(",") if part.strip()]
        for candidate in (real, forwarded[-1] if forwarded else ""):
            try:
                ipaddress.ip_address(candidate)
                return candidate
            except ValueError:
                continue
    return peer


def _username_failures(db: Session, username: str, since: datetime) -> int:
    last_success = db.query(func.max(LoginAttempt.created_at)).filter(
        LoginAttempt.username == username,
        LoginAttempt.success == True,
    ).scalar()
    if last_success and last_success > since:
        since = last_success
    return db.query(func.count(LoginAttempt.id)).filter(
        LoginAttempt.username == username,
        LoginAttempt.success == False,
        LoginAttempt.created_at > since,
    ).scalar()


def _ip_failures(db: Session, ip: str, since: datetime) -> int:
    return db.query(func.count(LoginAttempt.id)).filter(
        LoginAttempt.ip_address == ip,
        LoginAttempt.success == False,
        LoginAttempt.created_at > since,
    ).scalar()


def is_locked(db: Session, username: str, ip: Optional[str]) -> bool:
    since = datetime.utcnow() - WINDOW
    if _username_failures(db, username, since) >= MAX_FAILURES:
        return True
    ip = trackable_ip(ip)
    return bool(ip) and _ip_failures(db, ip, since) >= MAX_IP_FAILURES


def record_attempt(db: Session, username: str, ip: Optional[str], success: bool) -> None:
    """Stores the attempt and, when a failure starts a lock, logs it in ActivityLog."""
    ip_tracked = trackable_ip(ip)
    db.add(LoginAttempt(username=username, ip_address=ip_tracked, success=success))
    db.commit()
    if success:
        return

    since = datetime.utcnow() - WINDOW
    locked = []
    if _username_failures(db, username, since) == MAX_FAILURES:
        locked.append(f"usuario '{username}' ({MAX_FAILURES} intentos)")
    if ip_tracked and _ip_failures(db, ip_tracked, since) == MAX_IP_FAILURES:
        locked.append(f"IP {ip_tracked} ({MAX_IP_FAILURES} intentos)")
    if not locked:
        return

    try:
        user = db.query(User).filter(User.username == username).first()
        db.add(ActivityLog(
            user_id=user.id if user else None,
            action="LOGIN_BLOCKED",
            entity_type="SISTEMA",
            details=f"Login bloqueado 15 minutos por intentos fallidos: {', '.join(locked)}.",
            ip_address=ip_tracked,
        ))
        db.commit()
    except Exception as e:
        logger.error(f"Error logging login block: {e}")
        db.rollback()
