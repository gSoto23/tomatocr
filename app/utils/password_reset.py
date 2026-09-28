"""Password recovery links. The token is a JWT with purpose "reset", valid 1 hour and
tied to the current password hash: once the password changes, the link stops working,
so each link can be used only once."""
import hashlib
from datetime import datetime, timedelta
from typing import Optional

from jose import JWTError, jwt
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.models.activity import ActivityLog
from app.db.models.user import User

RESET_MINUTES = 60
MAX_REQUESTS_PER_HOUR = 3
MIN_PASSWORD_LENGTH = 8


def _fingerprint(user: User) -> str:
    return hashlib.sha256((user.hashed_password or "").encode()).hexdigest()[:16]


def make_token(user: User) -> str:
    expire = datetime.utcnow() + timedelta(minutes=RESET_MINUTES)
    return jwt.encode({"sub": user.username, "purpose": "reset", "pwd": _fingerprint(user), "exp": expire},
                      settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def user_from_token(db: Session, token: str) -> Optional[User]:
    try:
        data = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
    except JWTError:
        return None
    if data.get("purpose") != "reset":
        return None
    user = db.query(User).filter(User.username == data.get("sub")).first()
    if user is None or data.get("pwd") != _fingerprint(user):
        return None
    return user


def find_user(db: Session, identifier: str) -> Optional[User]:
    """By username or by e-mail (case-insensitive)."""
    identifier = (identifier or "").strip()
    if not identifier:
        return None
    user = db.query(User).filter(User.username == identifier).first()
    if user is None and "@" in identifier:
        matches = db.query(User).filter(User.email.ilike(identifier)).all()
        user = matches[0] if len(matches) == 1 else None
    return user


def too_many_requests(db: Session, user: User) -> bool:
    since = datetime.utcnow() - timedelta(hours=1)
    return db.query(ActivityLog).filter(ActivityLog.action == "PASSWORD_RESET_REQUEST",
                                        ActivityLog.entity_id == user.id,
                                        ActivityLog.created_at >= since).count() >= MAX_REQUESTS_PER_HOUR


def password_problem(new: str, confirm: str) -> Optional[str]:
    if len(new or "") < MIN_PASSWORD_LENGTH:
        return f"La contraseña nueva tiene que tener al menos {MIN_PASSWORD_LENGTH} caracteres"
    if new != confirm:
        return "Las dos contraseñas no coinciden"
    return None
