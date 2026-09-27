from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.core.roles import ADMIN
from app.core.templates import templates
from app.db.models.crm import Account, Contact, Opportunity
from app.db.models.project import Project
from app.db.models.quote import Quote
from app.db.models.reforestation import ReforestationProject
from app.db.models.user import User
from app.routers import deps
from app.utils.crm import dismiss_duplicate, find_duplicates, merge_accounts

# "Clientes" in the menu (docs/ANALISIS_ENCAJE_CRM.md, R7).
router = APIRouter(prefix="/clientes", tags=["clientes"])


def toast_redirect(url: str, message: str, error: bool = False) -> RedirectResponse:
    response = RedirectResponse(url=url, status_code=status.HTTP_303_SEE_OTHER)
    response.set_cookie(key="toast_message", value=message)
    if error:
        response.set_cookie(key="toast_type", value="error")
    return response


def account_summary(db: Session, account: Account) -> dict:
    return {
        "account": account,
        "contacts": db.query(Contact).filter(Contact.account_id == account.id).count(),
        "opportunities": db.query(Opportunity).filter(Opportunity.account_id == account.id).count(),
        "projects": [p.name for p in db.query(Project).filter(Project.account_id == account.id)],
        "quotes": db.query(Quote).filter(Quote.account_id == account.id).count(),
        "reforestation": db.query(ReforestationProject).filter(ReforestationProject.account_id == account.id).count(),
    }


@router.get("/duplicados")
def duplicates(request: Request, db: Session = Depends(deps.get_db), user: User = Depends(deps.require_roles(ADMIN))):
    pairs = [
        {"a": account_summary(db, a), "b": account_summary(db, b), "score": score}
        for a, b, score in find_duplicates(db)
    ]
    return templates.TemplateResponse("crm/duplicados.html", {"request": request, "user": user, "pairs": pairs})


def get_active_account(db: Session, account_id: int) -> Account:
    account = db.get(Account, account_id)
    if account is None or account.merged_into_id:
        raise HTTPException(status_code=404, detail="Cuenta no encontrada")
    return account


@router.post("/cuentas/{keep_id}/fusionar/{drop_id}")
def merge(keep_id: int, drop_id: int, db: Session = Depends(deps.get_db),
          user: User = Depends(deps.require_roles(ADMIN))):
    keep, drop = get_active_account(db, keep_id), get_active_account(db, drop_id)
    try:
        moved = merge_accounts(db, keep, drop, user)
    except ValueError as e:
        return toast_redirect("/clientes/duplicados", str(e), error=True)
    total = sum(moved.values())
    return toast_redirect("/clientes/duplicados", f"'{drop.name}' se fusionó en '{keep.name}' ({total} registros movidos)")


@router.post("/duplicados/{a_id}/{b_id}/descartar")
def not_duplicate(a_id: int, b_id: int, db: Session = Depends(deps.get_db),
                  user: User = Depends(deps.require_roles(ADMIN))):
    get_active_account(db, a_id), get_active_account(db, b_id)
    dismiss_duplicate(db, a_id, b_id, user)
    db.commit()
    return toast_redirect("/clientes/duplicados", "Marcadas como cuentas distintas")
