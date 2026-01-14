
from typing import Optional
from fastapi import APIRouter, Depends, Form, Request, status, HTTPException
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.db.session import SessionLocal
from app.db.models.user import User
from app.routers import deps
from app.core.security import get_password_hash
from sqlalchemy.exc import IntegrityError
from app.utils.activity import log_activity

router = APIRouter(
    prefix="/users",
    tags=["users"],
    dependencies=[Depends(deps.get_current_user)]
)

from app.core.templates import templates

def check_admin(user: User):
    if user.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized")

@router.get("/")
async def list_users(
    request: Request, 
    page: int = 1,
    limit: int = 10,
    db: Session = Depends(deps.get_db), 
    user: User = Depends(deps.get_current_user)
):
    check_admin(user)
    
    count_query = db.query(func.count(User.id))
    total_records = count_query.scalar()
    
    offset = (page - 1) * limit
    users = db.query(User)\
        .offset(offset)\
        .limit(limit)\
        .all()
        
    from math import ceil
    total_pages = ceil(total_records / limit)
    
    return templates.TemplateResponse("users/list.html", {
        "request": request, 
        "users": users, 
        "user": user,
        "page": page,
        "total_pages": total_pages,
        "total_records": total_records
    })

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
    phone: Optional[str] = Form(None),
    email: Optional[str] = Form(None),
    start_date: Optional[str] = Form(None),
    hourly_rate: Optional[float] = Form(None),
    monthly_salary: Optional[float] = Form(None),
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

    from datetime import datetime
    s_date = None
    if start_date:
        try:
            s_date = datetime.strptime(start_date, "%Y-%m-%d").date()
        except ValueError:
            pass            

    new_user = User(
        username=username,
        hashed_password=get_password_hash(password),
        full_name=full_name,
        role=role,
        phone=phone,
        email=email,
        start_date=s_date,
        hourly_rate=hourly_rate,
        monthly_salary=monthly_salary,
        is_active=is_active
    )
    db.add(new_user)
    db.commit()
    db.commit()
    
    # Audit Log
    log_activity(db, user, "CREATE", "USER", new_user.id, f"Created user {username} ({role})")
    
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
    phone: Optional[str] = Form(None),
    email: Optional[str] = Form(None),
    start_date: Optional[str] = Form(None),
    hourly_rate: Optional[float] = Form(None),
    monthly_salary: Optional[float] = Form(None),
    is_active: bool = Form(False),
    db: Session = Depends(deps.get_db),
    user: User = Depends(deps.get_current_user)
):
    check_admin(user)
    edit_user = db.query(User).filter(User.id == id).first()
    if edit_user:
        # Check for duplicate username
        existing_user = db.query(User).filter(User.username == username, User.id != id).first()
        if existing_user:
            response = RedirectResponse(url=f"/users/{id}/edit", status_code=status.HTTP_303_SEE_OTHER)
            response.set_cookie(key="toast_message", value="Error: Ese nombre de usuario ya está ocupado.")
            response.set_cookie(key="toast_type", value="error")
            return response

        from datetime import datetime
        s_date = None
        if start_date:
            try:
                s_date = datetime.strptime(start_date, "%Y-%m-%d").date()
            except ValueError:
                pass
            
        edit_user.username = username
        edit_user.full_name = full_name
        edit_user.role = role
        edit_user.phone = phone
        edit_user.email = email
        edit_user.start_date = s_date
        edit_user.hourly_rate = hourly_rate
        edit_user.monthly_salary = monthly_salary
        edit_user.is_active = is_active
        
        if password and password.strip():
             edit_user.hashed_password = get_password_hash(password)
             
        try:
            db.commit()
            # Audit Log
            log_activity(db, user, "UPDATE", "USER", edit_user.id, f"Updated user {username}")
        except IntegrityError:
            db.rollback()
            response = RedirectResponse(url=f"/users/{id}/edit", status_code=status.HTTP_303_SEE_OTHER)
            response.set_cookie(key="toast_message", value="Error: El nombre de usuario ya existe o hubo un problema de datos.")
            response.set_cookie(key="toast_type", value="error")
            return response
        except Exception as e:
            db.rollback()
            print(f"Error updating user: {e}")
            response = RedirectResponse(url=f"/users/{id}/edit", status_code=status.HTTP_303_SEE_OTHER)
            response.set_cookie(key="toast_message", value="Error interno al actualizar usuario.")
            response.set_cookie(key="toast_type", value="error")
            return response

    response = RedirectResponse(url="/users", status_code=status.HTTP_303_SEE_OTHER)
    response.set_cookie(key="toast_message", value="Usuario actualizado correctamente")
    return response

@router.post("/{id}/delete")
async def delete_user(
    id: int,
    db: Session = Depends(deps.get_db),
    user: User = Depends(deps.get_current_user)
):
    check_admin(user)
    
    # Prevent self-deletion
    if user.id == id:
        response = RedirectResponse(url=f"/users/{id}/edit", status_code=status.HTTP_303_SEE_OTHER)
        response.set_cookie(key="toast_message", value="Error: No puedes eliminar tu propio usuario.")
        response.set_cookie(key="toast_type", value="error")
        return response

    user_to_delete = db.query(User).filter(User.id == id).first()
    if not user_to_delete:
         raise HTTPException(status_code=404, detail="User not found")
         
    deleted_username = user_to_delete.username    
    db.delete(user_to_delete)
    db.commit()
    
    # Audit Log
    log_activity(db, user, "DELETE", "USER", id, f"Deleted user {deleted_username}")
    
    response = RedirectResponse(url="/users", status_code=status.HTTP_303_SEE_OTHER)
    response.set_cookie(key="toast_message", value="Usuario eliminado correctamente")
    return response
