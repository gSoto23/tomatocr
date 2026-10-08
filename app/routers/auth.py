
from fastapi import APIRouter, Depends, status, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
from app.db.models.user import User
from app.core.security import verify_password, create_access_token
from app.core.config import settings
from datetime import timedelta

from app.routers import deps
from app.utils.activity import log_activity
from app.utils import login_throttle

router = APIRouter()

def find_login_user(db: Session, typed: str):
    """The user for what was typed in "Usuario": the exact username (a space at either end
    doesn't count) or, with an @, the profile e-mail without regard to case, when only one
    user has it."""
    typed = (typed or "").strip()
    if not typed:
        return None
    found = db.query(User).filter(User.username == typed).first()
    if found is None and "@" in typed:
        from sqlalchemy import func
        matches = db.query(User).filter(func.lower(User.email) == typed.lower()).limit(2).all()
        found = matches[0] if len(matches) == 1 else None
    return found


@router.post("/login")
def login(
    request: Request,
    user: str = Form(""),
    pass_: str = Form("", alias="pass"), # mapping 'pass' from HTML form to 'pass_' variable
    db: Session = Depends(deps.get_db)
):
    if not user or not pass_:
        return RedirectResponse(url="/?error=invalid_credentials", status_code=status.HTTP_303_SEE_OTHER)

    client_ip = login_throttle.client_ip(request)
    # The username or the e-mail of the profile: people type their e-mail.
    db_user = find_login_user(db, user)
    # Failures count per account (whichever way it was typed), so typing the e-mail and the
    # username in turns doesn't double the attempts.
    key = db_user.username if db_user else user.strip().lower()
    if login_throttle.is_locked(db, key, client_ip):
        return RedirectResponse(url="/?error=too_many_attempts", status_code=status.HTTP_303_SEE_OTHER)

    # Authenticate. A wrong password never reveals whether the account exists or is
    # active; only someone who knows the password learns that the user is deactivated.
    if not db_user or not verify_password(pass_, db_user.hashed_password):
        login_throttle.record_attempt(db, key, client_ip, success=False)
        return RedirectResponse(url="/?error=invalid_credentials", status_code=status.HTTP_303_SEE_OTHER)
    if not deps.can_log_in(db_user):
        login_throttle.record_attempt(db, key, client_ip, success=False)
        return RedirectResponse(url="/?error=inactive", status_code=status.HTTP_303_SEE_OTHER)

    login_throttle.record_attempt(db, key, client_ip, success=True)

    # Create Token
    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": db_user.username, "role": db_user.role},
        expires_delta=access_token_expires
    )

    # Log activity
    log_activity(
        db=db,
        user=db_user,
        action="LOGIN",
        entity_type="SISTEMA",
        details=f"Usuario {db_user.username} inició sesión."
    )

    # Redirect to Dashboard with Cookie
    response = RedirectResponse(url="/dashboard", status_code=status.HTTP_303_SEE_OTHER)
    response.set_cookie(
        key="access_token",
        value=f"Bearer {access_token}",
        httponly=True,
        # secure solo en producción (Postgres/RDS): en local dev con SQLite
        # seguimos sirviendo por http y un cookie Secure no se guardaría.
        secure=not settings.USE_SQLITE,
        samesite="lax",
    )
    return response

@router.get("/logout")
def logout(
    request: Request,
    db: Session = Depends(deps.get_db)
):
    # Try to extract user from cookie if possible to log logout event
    token = request.cookies.get("access_token")
    if token:
        try:
            user = deps.get_current_user(request, db)
            if user:
                log_activity(
                    db=db,
                    user=user,
                    action="LOGOUT",
                    entity_type="SISTEMA",
                    details=f"Usuario {user.username} cerró sesión."
                )
        except Exception:
            pass # Ignore expired/invalid tokens on logout

    response = RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)
    response.delete_cookie("access_token")
    return response
