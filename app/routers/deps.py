from fastapi import Depends, HTTPException, status, Request
from jose import JWTError, jwt
from sqlalchemy.orm import Session
from app.db.session import SessionLocal
from app.core.config import settings
from app.core.roles import ALL_ROLES, CLIENT
from app.db.models.user import User

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def can_log_in(user: User) -> bool:
    # NULL is treated as active: only an explicit deactivation locks a user out.
    if user.is_active is False:
        return False
    return user.status not in ("inactive", "liquidated")

def get_current_user(request: Request, db: Session = Depends(get_db)) -> User:
    token = request.cookies.get("access_token")

    if not token:
        raise HTTPException(
            status_code=status.HTTP_303_SEE_OTHER,
            detail="Not authenticated",
            headers={"Location": "/?error=login_required"}
        )

    # Remove "Bearer " prefix if present
    if token.startswith("Bearer "):
        token = token.split(" ")[1]

    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            raise HTTPException(
                status_code=status.HTTP_303_SEE_OTHER,
                detail="Invalid credential",
                headers={"Location": "/?error=invalid_token"}
            )
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_303_SEE_OTHER,
            detail="Could not validate credentials",
            headers={"Location": "/?error=invalid_token"}
        )

    user = db.query(User).filter(User.username == username).first()
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_303_SEE_OTHER,
            detail="User not found",
            headers={"Location": "/?error=user_not_found"}
        )

    # A token issued before the user was deactivated must stop working too.
    if not can_log_in(user):
        raise HTTPException(
            status_code=status.HTTP_303_SEE_OTHER,
            detail="User inactive",
            headers={
                "Location": "/?error=login_required",
                "Set-Cookie": "access_token=; Max-Age=0; Path=/; HttpOnly; SameSite=Lax",
            }
        )

    return user

def require_sales(user: User = Depends(get_current_user)) -> User:
    """Clientes and the Cotizador's sales side: admin, ventas, or a supervisor marked "También vende"."""
    if not user.sells:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized")
    return user


def can_quote(user: User) -> bool:
    """The Cotizador: whoever sells, and the client (its own quotes)."""
    return user.sells or user.role == CLIENT


def require_quotes(user: User = Depends(get_current_user)) -> User:
    if not can_quote(user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized")
    return user


def require_roles(*roles: str):
    """Dependency that answers 403 unless the current user has one of `roles`."""
    unknown = set(roles) - ALL_ROLES
    if unknown:
        raise ValueError(f"Unknown roles: {unknown}")
    allowed = frozenset(roles)

    def dependency(user: User = Depends(get_current_user)) -> User:
        if user.role not in allowed:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized")
        return user

    return dependency
