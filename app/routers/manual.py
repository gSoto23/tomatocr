"""User manual: /manual and /manual/<chapter>. See app/utils/manual.py."""
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.core.templates import templates
from app.db.models.user import User
from app.routers import deps
from app.utils.crm import funnel, funnel_period
from app.utils.manual import BY_SLUG, chapters_for, help_url

router = APIRouter(prefix="/manual", tags=["manual"])

templates.env.globals["manual_help_url"] = help_url


def chapter_context(db: Session, slug: str) -> dict:
    """Live values some chapters quote (e.g. the pilot period and goals)."""
    if slug == "clientes":
        period = funnel_period(db)
        return {"period": period, "funnel": funnel(db, period=period)}
    return {}


@router.get("")
@router.get("/")
def index(request: Request, user: User = Depends(deps.get_current_user)):
    return templates.TemplateResponse("manual/index.html", {
        "request": request, "user": user, "chapters": chapters_for(user.role, user.sells), "current": None,
    })


@router.get("/{slug}")
def chapter(slug: str, request: Request, db: Session = Depends(deps.get_db),
            user: User = Depends(deps.get_current_user)):
    item = BY_SLUG.get(slug)
    if item is None or not item.allowed(user.role, user.sells):
        raise HTTPException(status_code=404, detail="Capítulo no encontrado")
    chapters = chapters_for(user.role, user.sells)
    position = chapters.index(item)
    return templates.TemplateResponse(f"manual/{slug}.html", {
        "request": request, "user": user, "chapters": chapters, "current": item,
        "previous": chapters[position - 1] if position else None,
        "next": chapters[position + 1] if position + 1 < len(chapters) else None,
        **chapter_context(db, slug),
    })
