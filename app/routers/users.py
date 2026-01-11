
from typing import Optional
from fastapi import APIRouter, Depends, Form, Request, status, HTTPException
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.db.models.user import User
from app.routers import deps
from app.core.security import get_password_hash

router = APIRouter(
    prefix="/users",
    tags=["users"],
    dependencies=[Depends(deps.get_current_user)]
)

templates = Jinja2Templates(directory="app/templates")

def check_admin(user: User):
    if user.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized")

@router.get("/")
async def list_users(request: Request, db: Session = Depends(deps.get_db), user: User = Depends(deps.get_current_user)):
    check_admin(user)
    users = db.query(User).all()
    return templates.TemplateResponse("users/list.html", {"request": request, "users": users, "user": user})

@router.get("/new")
async def new_user_form(request: Request, user: User = Depends(deps.get_current_user)):
    check_admin(user)
    return templates.TemplateResponse("users/form.html", {"request": request, "user": user, "edit_user": None})

@router.post("/new")
async def create_user(
    username: str = Form(...),
    password: str = Form(...),
    full_name: str = Form(...),
    role: str = Form(...),
    is_active: bool = Form(False),
    db: Session = Depends(deps.get_db),
    user: User = Depends(deps.get_current_user)
):
    check_admin(user)
    
    # Check if user exists
    existing = db.query(User).filter(User.username == username).first()
    if existing:
         response = RedirectResponse(url="/users/new", status_code=status.HTTP_303_SEE_OTHER)
         response.set_cookie(key="toast_message", value="El nombre de usuario ya existe")
         response.set_cookie(key="toast_type", value="error")
         return response

    new_user = User(
        username=username,
        hashed_password=get_password_hash(password),
        full_name=full_name,
        role=role,
        is_active=is_active
    )
    db.add(new_user)
    db.commit()
    db.commit()
    response = RedirectResponse(url="/users", status_code=status.HTTP_303_SEE_OTHER)
    response.set_cookie(key="toast_message", value="Usuario creado correctamente")
    return response

@router.get("/{id}/edit")
async def edit_user_form(id: int, request: Request, db: Session = Depends(deps.get_db), user: User = Depends(deps.get_current_user)):
    check_admin(user)
    edit_user = db.query(User).filter(User.id == id).first()
    if not edit_user:
        return RedirectResponse(url="/users", status_code=status.HTTP_303_SEE_OTHER)
    return templates.TemplateResponse("users/form.html", {"request": request, "user": user, "edit_user": edit_user})

@router.post("/{id}/edit")
async def update_user(
    id: int,
    username: str = Form(...),
    password: Optional[str] = Form(None),
    full_name: str = Form(...),
    role: str = Form(...),
    is_active: bool = Form(False),
    db: Session = Depends(deps.get_db),
    user: User = Depends(deps.get_current_user)
):
    check_admin(user)
    edit_user = db.query(User).filter(User.id == id).first()
    if edit_user:
        edit_user.username = username
        edit_user.full_name = full_name
        edit_user.role = role
        edit_user.is_active = is_active
        
        if password and password.strip():
             edit_user.hashed_password = get_password_hash(password)
             
        db.commit()
        db.commit()
    response = RedirectResponse(url="/users", status_code=status.HTTP_303_SEE_OTHER)
    response.set_cookie(key="toast_message", value="Usuario actualizado correctamente")
    return response
