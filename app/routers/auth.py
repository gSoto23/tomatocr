
from fastapi import APIRouter, Depends, HTTPException, status, Form, Request
from fastapi.responses import RedirectResponse, HTMLResponse
from sqlalchemy.orm import Session
from app.db.session import SessionLocal
from app.db.models.user import User
from app.core.security import verify_password, create_access_token
from app.core.config import settings
from datetime import timedelta

router = APIRouter()

# Dependency
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@router.post("/login")
async def login(
    request: Request,
    user: str = Form(...),
    pass_: str = Form(..., alias="pass"), # mapping 'pass' from HTML form to 'pass_' variable
    db: Session = Depends(get_db)
):
    # Authenticate
    db_user = db.query(User).filter(User.username == user).first()
    if not db_user or not verify_password(pass_, db_user.hashed_password):
        # Return to login with error (simplified for now, ideally show error message)
        # For HTMX or API, we return 401. For standard form, we might redirect back.
        # Let's redirect back with a query param for error ?error=1
        return RedirectResponse(url="/?error=invalid_credentials", status_code=status.HTTP_303_SEE_OTHER)

    # Create Token
    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": db_user.username, "role": db_user.role},
        expires_delta=access_token_expires
    )

    # Redirect to Dashboard with Cookie
    response = RedirectResponse(url="/dashboard", status_code=status.HTTP_303_SEE_OTHER)
    response.set_cookie(key="access_token", value=f"Bearer {access_token}", httponly=True)
    return response

@router.get("/logout")
async def logout():
    response = RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)
    response.delete_cookie("access_token")
    return response
