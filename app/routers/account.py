"""The person's own account: change the password from inside, and recover it by e-mail
("¿Olvidaste tu contraseña?"). app/utils/password_reset.py."""
from fastapi import APIRouter, BackgroundTasks, Depends, Form, Request, status
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.core.security import get_password_hash, verify_password
from app.core.templates import templates
from app.db.models.user import User
from app.routers import deps
from app.utils import password_reset
from app.utils.activity import log_activity
from app.utils.email import send_plain_email

router = APIRouter(tags=["cuenta"])

SITE = "https://tomatocr.com"


def toast(url: str, message: str, error: bool = False) -> RedirectResponse:
    response = RedirectResponse(url=url, status_code=status.HTTP_303_SEE_OTHER)
    response.set_cookie(key="toast_message", value=message)
    if error:
        response.set_cookie(key="toast_type", value="error")
    return response


# --- Change it from inside ------------------------------------------------------------

@router.get("/cuenta/contrasena")
def change_password_form(request: Request, user: User = Depends(deps.get_current_user)):
    return templates.TemplateResponse("account/password.html", {"request": request, "user": user})


@router.post("/cuenta/contrasena")
def change_password(current: str = Form(""), new: str = Form(""), confirm: str = Form(""),
                    db: Session = Depends(deps.get_db), user: User = Depends(deps.get_current_user)):
    if not verify_password(current, user.hashed_password):
        return toast("/cuenta/contrasena", "La contraseña actual no es correcta", error=True)
    problem = password_reset.password_problem(new, confirm)
    if problem:
        return toast("/cuenta/contrasena", problem, error=True)
    user.hashed_password = get_password_hash(new)
    db.commit()
    log_activity(db, user, "UPDATE", "USER", user.id, "Cambió su contraseña")
    return toast("/dashboard", "Contraseña cambiada")


# --- Recover it by e-mail -------------------------------------------------------------

@router.api_route("/recuperar", methods=["GET", "HEAD"])
def recover_form(request: Request):
    return templates.TemplateResponse("account/recover.html", {"request": request,
                                                               "sent": request.query_params.get("enviado")})


@router.post("/recuperar")
def recover(background: BackgroundTasks, request: Request, identifier: str = Form(""),
            db: Session = Depends(deps.get_db)):
    """Always answers the same, so it never reveals which users or e-mails exist."""
    user = password_reset.find_user(db, identifier)
    if user and user.email and deps.can_log_in(user) and not password_reset.too_many_requests(db, user):
        link = f"{SITE}/recuperar/{password_reset.make_token(user)}"
        body = "\n".join([
            f"Hola {user.full_name or user.username}:",
            "",
            "Recibimos una solicitud para cambiar tu contraseña del sistema TOMATO.",
            f"Para elegir una nueva, abrí este enlace (vence en {password_reset.RESET_MINUTES} minutos):",
            "",
            link,
            "",
            "Si no fuiste vos, ignorá este correo: tu contraseña sigue igual.",
            "",
            f"Tu usuario es: {user.username}",
        ])
        background.add_task(send_plain_email, [user.email], "Cambiar tu contraseña de TOMATO", body)
        log_activity(db, user, "PASSWORD_RESET_REQUEST", "USER", user.id, "Pidió recuperar la contraseña")
    return RedirectResponse(url="/recuperar?enviado=1", status_code=status.HTTP_303_SEE_OTHER)


@router.get("/recuperar/{token}")
def reset_form(token: str, request: Request, db: Session = Depends(deps.get_db)):
    user = password_reset.user_from_token(db, token)
    return templates.TemplateResponse("account/reset.html", {
        "request": request, "token": token, "valid": user is not None, "username": user.username if user else None,
    })


@router.post("/recuperar/{token}")
def reset(token: str, request: Request, new: str = Form(""), confirm: str = Form(""),
          db: Session = Depends(deps.get_db)):
    user = password_reset.user_from_token(db, token)
    if user is None:
        return templates.TemplateResponse("account/reset.html", {"request": request, "token": token, "valid": False,
                                                                  "username": None}, status_code=400)
    problem = password_reset.password_problem(new, confirm)
    if problem:
        return templates.TemplateResponse("account/reset.html", {"request": request, "token": token, "valid": True,
                                                                  "username": user.username, "error": problem},
                                          status_code=400)
    user.hashed_password = get_password_hash(new)
    db.commit()
    log_activity(db, user, "UPDATE", "USER", user.id, "Cambió su contraseña con el enlace de recuperación")
    return RedirectResponse(url="/?ok=password_reset", status_code=status.HTTP_303_SEE_OTHER)
