"""Read-only sync of the reforestation trees for darboles.com (server to server).
Contract: docs/INTEGRACION_DARBOLES.md, "Sincronización de árboles". tomatocr.com is the source
of truth; darboles.com only reads and never writes here."""
import hmac
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from sqlalchemy.orm import Session, selectinload

from app.core.config import settings
from app.db.models.reforestation import (KIND_INSTITUCIONAL, LOCATION_TREE, ReforestationProject, ReforestationTree,
                                         TreeCheck)
from app.routers import deps
from app.utils.reforestation import public_visits, shows_visit_details

router = APIRouter(tags=["darboles"])

DEFAULT_LIMIT = 500
MAX_LIMIT = 1000


def require_sync_key(x_api_key: Optional[str] = Header(None)):
    """Its own read-only key, different from DARBOLES_API_KEY (leads). No CORS: only a server
    that holds the key can call it."""
    if not settings.DARBOLES_SYNC_API_KEY:
        raise HTTPException(status_code=503, detail="Sincronización de árboles no configurada")
    if not x_api_key or not hmac.compare_digest(x_api_key, settings.DARBOLES_SYNC_API_KEY):
        raise HTTPException(status_code=401, detail="Clave inválida")


def iso_utc(value: Optional[datetime]) -> Optional[str]:
    return value.replace(microsecond=0).isoformat() + "Z" if value else None


def project_payload(project: ReforestationProject) -> dict:
    public = shows_visit_details(project)
    return {"id": project.id, "name": project.public_name if public else "Proyecto institucional", "public": public}


def tree_payload(tree: ReforestationTree) -> dict:
    return {
        "id": tree.id,
        "project": project_payload(tree.project),
        "tree_number": tree.tree_number,
        "species": tree.species,
        "sector": tree.sector_name,
        "lat": tree.lat,
        "lng": tree.lng,
        "location_precision": "tree" if tree.location_source == LOCATION_TREE else "sector",
        "date_planted": tree.date_planted.isoformat() if tree.date_planted else None,
        "status": tree.status,
        "last_checked_at": tree.last_checked_at.isoformat() if tree.last_checked_at else None,
        "replaced_by_id": tree.replaced_by_id,
        "updated_at": iso_utc(tree.updated_at),
        "visits": public_visits(tree),
    }


def parse_since(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        moment = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        raise HTTPException(status_code=400, detail="updated_since debe ser una fecha ISO en UTC")
    return moment.astimezone(timezone.utc).replace(tzinfo=None) if moment.tzinfo else moment


@router.get("/api/darboles/trees", dependencies=[Depends(require_sync_key)])
def darboles_trees(cursor: Optional[str] = None, limit: int = Query(DEFAULT_LIMIT, ge=1, le=MAX_LIMIT),
                   updated_since: Optional[str] = None, db: Session = Depends(deps.get_db)):
    """Institutional trees with coordinates, by id; `next_cursor` is null on the last page."""
    after = 0
    if cursor:
        if not cursor.isdigit():
            raise HTTPException(status_code=400, detail="cursor no válido")
        after = int(cursor)
    since = parse_since(updated_since)
    query = db.query(ReforestationTree).join(ReforestationProject).filter(
        ReforestationProject.kind == KIND_INSTITUCIONAL, ReforestationTree.id > after,
        ReforestationTree.lat.isnot(None), ReforestationTree.lng.isnot(None))
    if since:
        query = query.filter(ReforestationTree.updated_at >= since)
    trees = query.options(selectinload(ReforestationTree.project),
                          selectinload(ReforestationTree.checks).selectinload(TreeCheck.photos)).order_by(
        ReforestationTree.id).limit(limit + 1).all()
    page, more = trees[:limit], len(trees) > limit
    return {
        "generated_at": iso_utc(datetime.utcnow()),
        "next_cursor": str(page[-1].id) if more else None,
        "trees": [tree_payload(t) for t in page],
    }
