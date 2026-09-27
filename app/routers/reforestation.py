from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Request, status
from fastapi.responses import StreamingResponse, RedirectResponse
from sqlalchemy.orm import Session
from typing import Optional
from app.routers import deps
from app.core.roles import ADMIN, SUPERVISOR, WORKER
from app.core.storage import s3_service
from app.db.models.log import DailyLog
from app.db.models.project import Project
from app.db.models.reforestation import (
    CHECK_STATUSES, KIND_INSTITUCIONAL, STATUS_REPLACED, ReforestationProject, ReforestationTree,
)
from app.db.models.user import User
from app.core.templates import templates
from app.utils.activity import log_activity
from app.utils.reforestation import (
    CSV_COLUMNS, CsvRejected, decode_csv, import_inventory_csv, inventory_rows, parse_date, parse_tree_numbers,
    record_check, survival_summary,
)
from app.utils.uploads import IMAGE_TYPES, MAX_IMAGE_SIZE_BYTES, read_validated_upload
from datetime import date
from io import BytesIO
import csv
import re
import unicodedata
from io import StringIO
from urllib.parse import quote

router = APIRouter(
    tags=["reforestation_admin"],
)

MONITORING_ROLES = (ADMIN, SUPERVISOR, WORKER)


def require_admin(current_user: User = Depends(deps.get_current_user)) -> User:
    if current_user.role != ADMIN:
        raise HTTPException(status_code=403, detail="Not authorized")
    return current_user


def get_reforestation_project(db: Session, project_id: int) -> ReforestationProject:
    project = db.query(ReforestationProject).filter(ReforestationProject.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


def read_csv_upload(file: UploadFile, content: bytes):
    if not file.filename.lower().endswith('.csv'):
        raise HTTPException(status_code=400, detail="Solo se aceptan archivos CSV.")
    return decode_csv(content)


def toast_redirect(url: str, message: str, error: bool = False) -> RedirectResponse:
    response = RedirectResponse(url=url, status_code=status.HTTP_303_SEE_OTHER)
    response.set_cookie(key="toast_message", value=message)
    if error:
        response.set_cookie(key="toast_type", value="error")
    return response


# --- Admin -------------------------------------------------------------------

@router.get("/dashboard/reforestacion")
def get_admin_dashboard(request: Request, db: Session = Depends(deps.get_db), current_user: User = Depends(require_admin)):
    projects = db.query(ReforestationProject).order_by(ReforestationProject.id).all()
    rows = [{"project": p, "summary": survival_summary(p.trees)} for p in projects]
    operations_projects = db.query(Project).order_by(Project.name).all()
    return templates.TemplateResponse("reforestation/admin.html", {
        "request": request, "user": current_user, "rows": rows,
        "operations_projects": operations_projects,
    })

@router.post("/dashboard/reforestacion/upload-csv")
async def upload_csv(
    client_name: str = Form(...),
    file: UploadFile = File(...),
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(require_admin)
):
    """Full inventory CSV (same columns as the download). Adds and updates trees and
    their monitoring; never deletes, and empty cells never erase stored data."""
    reader = read_csv_upload(file, await file.read())
    client_name = client_name.strip()
    project = db.query(ReforestationProject).filter(ReforestationProject.client_name == client_name).first()
    if not project:
        project = ReforestationProject(client_name=client_name)
        db.add(project)
        db.flush()
    try:
        result = import_inventory_csv(db, project, reader, user_id=current_user.id)
    except CsvRejected as e:
        db.rollback()
        raise HTTPException(status_code=400, detail="No se importó nada. " + " | ".join(e.errors))

    message = f"{client_name}: {result['created']} árboles nuevos, {result['updated']} actualizados"
    if result["checks_added"] or result["checks_updated"]:
        message += f", {result['checks_added']} monitoreos nuevos y {result['checks_updated']} corregidos"
    message += "."
    if result["not_in_file"]:
        message += f" {result['not_in_file']} árboles registrados no venían en el archivo y se conservaron."
    log_activity(db, current_user, "IMPORT", "REFORESTATION", project.id, message)
    return {"message": message}

@router.post("/dashboard/reforestacion/{project_id}/settings")
def update_settings(
    project_id: int,
    linked_project_id: Optional[str] = Form(None),
    is_public: bool = Form(False),
    public_name: Optional[str] = Form(None),
    consent_date: Optional[str] = Form(None),
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(require_admin)
):
    project = get_reforestation_project(db, project_id)
    url = "/dashboard/reforestacion"
    linked = None
    if linked_project_id:
        linked = db.query(Project).filter(Project.id == int(linked_project_id)).first() if linked_project_id.isdigit() else None
        if linked is None:
            return toast_redirect(url, "El proyecto de operaciones no existe", error=True)
    public_name = (public_name or "").strip() or None
    if is_public and not public_name:
        return toast_redirect(url, "Para autorizar el nombre en el mapa, escriba el nombre público", error=True)
    try:
        consent = parse_date(consent_date) if (consent_date or "").strip() else None
    except ValueError as e:
        return toast_redirect(url, f"Fecha de autorización: {e}", error=True)

    project.project_id = linked.id if linked else None
    project.is_public = is_public
    project.public_name = public_name
    project.consent_date = consent
    db.commit()
    log_activity(db, current_user, "UPDATE", "REFORESTATION", project.id,
                 f"Configuración: nombre público {'autorizado' if is_public else 'no autorizado'}")
    return toast_redirect(url, "Configuración guardada")


def csv_response(rows, filename: str) -> StreamingResponse:
    output = StringIO()
    writer = csv.writer(output)
    writer.writerow(CSV_COLUMNS)
    writer.writerows(rows)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": content_disposition(filename)}
    )


@router.get("/dashboard/reforestacion/download-csv/{project_id}")
def download_csv(
    project_id: int, 
    db: Session = Depends(deps.get_db), 
    current_user: User = Depends(require_admin)
):
    """Every column, empty where there is no data yet: fill in, then import again."""
    project = get_reforestation_project(db, project_id)
    filename = f"{(project.client_name or 'proyecto').replace(' ', '_')}_inventario.csv"
    return csv_response(inventory_rows(project), filename)


@router.get("/dashboard/reforestacion/plantilla-csv")
def download_template(current_user: User = Depends(require_admin)):
    """Empty inventory with every column and one example row."""
    example = [1, "Guanacaste", "Parque central", 10.0163, -84.2116, "2026-06-01", "", "", "", "", ""]
    return csv_response([example], "plantilla_inventario_arboles.csv")


def content_disposition(filename: str) -> str:
    """Attachment header that survives non-ASCII names (RFC 6266 / RFC 5987).

    HTTP headers are latin-1, so a name like "Árbol" can't go in `filename`
    as-is: that gets an ASCII fallback, and browsers use `filename*` instead.
    """
    ascii_name = unicodedata.normalize("NFKD", filename).encode("ascii", "ignore").decode("ascii")
    ascii_name = re.sub(r'[^A-Za-z0-9._-]', "_", ascii_name) or "inventario.csv"
    return f"attachment; filename=\"{ascii_name}\"; filename*=UTF-8''{quote(filename, safe='')}"


# --- Field monitoring (from an operations project linked to a reforestation project)

def get_monitoring_context(db: Session, project_id: int, user: User):
    """Admin and supervisors monitor any linked project; workers only assigned ones."""
    if user.role not in MONITORING_ROLES:
        raise HTTPException(status_code=403, detail="Not authorized")
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    if user.role == WORKER and user.id not in [u.id for u in project.users]:
        raise HTTPException(status_code=403, detail="Not authorized")
    reforestation = db.query(ReforestationProject).filter(ReforestationProject.project_id == project.id).first()
    if not reforestation:
        raise HTTPException(status_code=404, detail="Este proyecto no tiene árboles vinculados")
    return project, reforestation


@router.get("/projects/{project_id}/monitoreo")
def monitoring_form(
    project_id: int,
    request: Request,
    db: Session = Depends(deps.get_db),
    user: User = Depends(deps.get_current_user)
):
    project, reforestation = get_monitoring_context(db, project_id, user)
    sectors = sorted({t.sector_name for t in reforestation.trees if t.sector_name})
    return templates.TemplateResponse("reforestation/monitoring.html", {
        "request": request, "user": user, "project": project, "reforestation": reforestation,
        "sectors": sectors, "statuses": CHECK_STATUSES, "today": date.today(),
        "summary": survival_summary(reforestation.trees),
    })


@router.post("/projects/{project_id}/monitoreo")
async def save_monitoring(
    project_id: int,
    checked_at: str = Form(...),
    mode: str = Form(...),
    tree_numbers: Optional[str] = Form(None),
    sector: Optional[str] = Form(None),
    check_status: str = Form(..., alias="status"),
    height_cm: Optional[str] = Form(None),
    notes: Optional[str] = Form(None),
    replaced_by: Optional[str] = Form(None),
    photo: Optional[UploadFile] = File(None),
    db: Session = Depends(deps.get_db),
    user: User = Depends(deps.get_current_user)
):
    project, reforestation = get_monitoring_context(db, project_id, user)
    url = f"/projects/{project_id}/monitoreo"
    trees_by_number = {t.tree_number: t for t in reforestation.trees}

    try:
        day = parse_date(checked_at)
        if day > date.today():
            raise ValueError("la fecha no puede ser futura")
        if check_status not in CHECK_STATUSES:
            raise ValueError("estado no válido")
        if mode == "sector":
            selected = [t for t in reforestation.trees if sector and t.sector_name == sector]
            if not selected:
                raise ValueError("ese sector no tiene árboles")
        else:
            numbers = parse_tree_numbers(tree_numbers)
            unknown = [n for n in numbers if n not in trees_by_number]
            if unknown:
                raise ValueError(f"no existen en este proyecto: {', '.join(map(str, unknown[:15]))}")
            selected = [trees_by_number[n] for n in numbers]
        height = float(height_cm.replace(",", ".")) if (height_cm or "").strip() else None
        replacement = None
        if (replaced_by or "").strip():
            if check_status != STATUS_REPLACED or len(selected) != 1:
                raise ValueError("'reemplazado por' solo aplica a un único árbol con estado reemplazado")
            replacement = trees_by_number.get(int(replaced_by)) if replaced_by.strip().isdigit() else None
            if replacement is None or replacement is selected[0]:
                raise ValueError("'reemplazado por' debe ser otro árbol de este proyecto")
    except ValueError as e:
        return toast_redirect(url, f"No se guardó: {e}", error=True)

    photo_path = None
    if photo is not None and photo.filename:
        contents, ext = await read_validated_upload(photo, IMAGE_TYPES, MAX_IMAGE_SIZE_BYTES)
        photo_path = s3_service.upload_file(BytesIO(contents), f"monitoreo{ext}", photo.content_type)
        if not photo_path:
            return toast_redirect(url, "No se guardó: no se pudo subir la foto. Intente de nuevo.", error=True)

    daily_log = db.query(DailyLog).filter(
        DailyLog.project_id == project.id, DailyLog.user_id == user.id, DailyLog.date == day
    ).order_by(DailyLog.id.desc()).first()
    for tree in selected:
        record_check(tree, day, check_status, height_cm=height, notes=notes, photo_path=photo_path,
                     user_id=user.id, daily_log_id=daily_log.id if daily_log else None, replaced_by=replacement)
    db.commit()
    log_activity(db, user, "CREATE", "TREE_CHECKS", reforestation.id,
                 f"Monitoreo {day}: {len(selected)} árboles {check_status}")
    return toast_redirect(url, f"Monitoreo guardado: {len(selected)} árboles marcados como {check_status}")


# --- Public map -----------------------------------------------------------------

public_router = APIRouter(prefix="/api/reforestation", tags=["reforestation_api"])

@public_router.get("/map-data")
def get_map_data(db: Session = Depends(deps.get_db)):
    """Institutional projects only. The client's name only with its authorization;
    never notes, photos or users."""
    projects = db.query(ReforestationProject).filter(
        ReforestationProject.kind == KIND_INSTITUCIONAL
    ).order_by(ReforestationProject.id).all()

    trees, summaries, anonymous = [], [], 0
    for project in projects:
        if project.is_public and project.public_name:
            name = project.public_name
        else:
            anonymous += 1
            name = "Proyecto institucional" if anonymous == 1 else f"Proyecto institucional {anonymous}"
        summary = survival_summary(project.trees)
        cohort = summary.cohorts[12]
        summaries.append({
            "project": name,
            "planted": summary.planted,
            "survival_12m": cohort.survival_pct,
            "verified_12m": cohort.verified_pct,
            "last_check": summary.last_check.isoformat() if summary.last_check else None,
        })
        for t in project.trees:
            if t.lat is None or t.lng is None:
                continue  # coordinates not loaded yet
            trees.append({
                "id": t.tree_number,
                "project": name,
                "sector": t.sector_name,
                "species": t.species,
                "lat": t.lat,
                "lng": t.lng,
                "date": t.date_planted.strftime("%Y-%m-%d") if t.date_planted else "N/A",
                "status": t.status,
            })
    return {"trees": trees, "projects": summaries}
