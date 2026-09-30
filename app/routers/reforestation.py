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
    CHECK_STATUSES, KIND_INSTITUCIONAL, PUBLIC_COMMENT_MAX, STATUS_REPLACED, ReforestationProject, ReforestationTree,
    TreeCheck,
)
from app.db.models.user import User
from app.core.templates import templates
from app.utils.activity import log_activity
from app.utils.reforestation import (
    CSV_COLUMNS, CsvRejected, decode_csv, import_inventory_csv, inventory_rows, name_key, parse_date,
    parse_tree_numbers, public_visits, record_check, refresh_tree_status, survival_summary,
)
from app.utils.uploads import PHOTO_RULES, process_photo_sized
from typing import List
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
MAX_VISIT_PHOTOS = 6
VISIT_PHOTO_MAX_SIDE = 1600
# Who can remove a wrong monitoring entry (trees and whole projects: admin only).
CHECK_DELETE_ROLES = (ADMIN, SUPERVISOR)


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
    client_name: str = Form(""),
    file: UploadFile = File(...),
    reforestation_id: Optional[int] = Form(None),
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(require_admin)
):
    """Full inventory CSV (same columns as the download). Adds and updates trees and
    their monitoring; never deletes, and empty cells never erase stored data."""
    reader = read_csv_upload(file, await file.read())
    client_name = " ".join(client_name.split())
    if reforestation_id:
        project = get_reforestation_project(db, reforestation_id)
        client_name = project.client_name
    else:
        if not client_name:
            raise HTTPException(status_code=400, detail="Elegí el proyecto o escribí el nombre del nuevo.")
        # "municipalidad  de alajuela" is the same client as "Municipalidad de Alajuela".
        key = name_key(client_name)
        project = next((p for p in db.query(ReforestationProject) if name_key(p.client_name) == key), None)
        if project:
            client_name = project.client_name
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
    # What darboles.com may show changes with the authorization: its next sync must see it.
    from datetime import datetime as _dt
    for tree in project.trees:
        tree.updated_at = _dt.utcnow()
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

@router.post("/dashboard/reforestacion/{project_id}/rename")
def rename_project(project_id: int, client_name: str = Form(...), db: Session = Depends(deps.get_db),
                   current_user: User = Depends(require_admin)):
    project = get_reforestation_project(db, project_id)
    url = "/dashboard/reforestacion"
    new_name = " ".join(client_name.split())
    if not new_name:
        return toast_redirect(url, "El nombre no puede quedar vacío", error=True)
    clash = next((p for p in db.query(ReforestationProject)
                  if p.id != project.id and name_key(p.client_name) == name_key(new_name)), None)
    if clash:
        return toast_redirect(url, f"Ya existe el proyecto «{clash.client_name}»", error=True)
    old = project.client_name
    project.client_name = new_name
    db.commit()
    log_activity(db, current_user, "UPDATE", "REFORESTATION", project.id, f"Renombró «{old}» a «{new_name}»")
    return toast_redirect(url, f"Proyecto renombrado a «{new_name}»")


@router.post("/dashboard/reforestacion/{project_id}/delete")
def delete_project(project_id: int, confirm_name: str = Form(""), db: Session = Depends(deps.get_db),
                   current_user: User = Depends(require_admin)):
    """Deletes a project with all its trees and monitoring (for one imported by mistake).
    The name must be typed again, so it can't happen by accident."""
    project = get_reforestation_project(db, project_id)
    url = "/dashboard/reforestacion"
    if name_key(confirm_name) != name_key(project.client_name):
        return toast_redirect(url, "Para borrar, escribí el nombre exacto del proyecto", error=True)
    name, trees = project.client_name, len(project.trees)
    for tree in project.trees:  # replacements point between trees of the same project
        tree.replaced_by = None
    db.flush()
    db.delete(project)
    db.commit()
    log_activity(db, current_user, "DELETE", "REFORESTATION", project_id, f"Borró «{name}» con {trees} árboles")
    return toast_redirect(url, f"Proyecto «{name}» borrado")


@router.post("/dashboard/reforestacion/{project_id}/trees/delete")
def delete_tree(project_id: int, tree_number: str = Form(...), db: Session = Depends(deps.get_db),
                current_user: User = Depends(require_admin)):
    project = get_reforestation_project(db, project_id)
    url = "/dashboard/reforestacion"
    number = int(tree_number) if tree_number.strip().isdigit() else None
    tree = next((t for t in project.trees if t.tree_number == number), None)
    if tree is None:
        return toast_redirect(url, f"«{project.client_name}» no tiene el árbol N° {tree_number}", error=True)
    for other in project.trees:
        if other.replaced_by_id == tree.id:
            other.replaced_by = None
    project.trees.remove(tree)
    db.commit()
    log_activity(db, current_user, "DELETE", "REFORESTATION", project.id,
                 f"Borró el árbol N° {number} de «{project.client_name}» y sus monitoreos")
    return toast_redirect(url, f"Árbol N° {number} borrado")


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
    recent = []
    if user.role in CHECK_DELETE_ROLES:
        recent = db.query(TreeCheck).join(ReforestationTree).filter(
            ReforestationTree.project_id == reforestation.id
        ).order_by(TreeCheck.created_at.desc(), TreeCheck.id.desc()).limit(20).all()
    return templates.TemplateResponse("reforestation/monitoring.html", {
        "request": request, "user": user, "project": project, "reforestation": reforestation,
        "sectors": sectors, "statuses": CHECK_STATUSES, "today": date.today(),
        "summary": survival_summary(reforestation.trees), "recent": recent,
        "public_project": bool(reforestation.is_public and reforestation.public_name),
        "max_photos": MAX_VISIT_PHOTOS, "comment_max": PUBLIC_COMMENT_MAX,
    })


@router.post("/projects/{project_id}/monitoreo/{check_id}/delete")
def delete_check(project_id: int, check_id: int, db: Session = Depends(deps.get_db),
                 user: User = Depends(deps.get_current_user)):
    """Removes a wrong monitoring entry; the tree goes back to its previous status."""
    if user.role not in CHECK_DELETE_ROLES:
        raise HTTPException(status_code=403, detail="Not authorized")
    project, reforestation = get_monitoring_context(db, project_id, user)
    url = f"/projects/{project_id}/monitoreo"
    check = db.query(TreeCheck).join(ReforestationTree).filter(
        TreeCheck.id == check_id, ReforestationTree.project_id == reforestation.id).first()
    if not check:
        return toast_redirect(url, "Ese monitoreo no existe", error=True)
    tree = check.tree
    details = f"Borró el monitoreo del árbol N° {tree.tree_number} ({check.status}, {check.checked_at:%d/%m/%Y})"
    tree.checks.remove(check)
    refresh_tree_status(tree)
    db.commit()
    log_activity(db, user, "DELETE", "TREE_CHECKS", reforestation.id, details)
    return toast_redirect(url, f"Monitoreo del árbol N° {tree.tree_number} borrado")


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
    public_comment: Optional[str] = Form(None),
    replaced_by: Optional[str] = Form(None),
    photos: List[UploadFile] = File(default=[]),
    photo: Optional[UploadFile] = File(None),
    visit_lat: Optional[str] = Form(None),
    visit_lng: Optional[str] = Form(None),
    visit_accuracy: Optional[str] = Form(None),
    use_as_tree_location: bool = Form(False),
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
        height = None
        if (height_cm or "").strip():
            try:
                height = float(height_cm.strip().replace(",", "."))
            except ValueError:
                raise ValueError("la altura tiene que ser un número en centímetros (ej. 45 o 45,5)")
            if height < 0:
                raise ValueError("la altura no puede ser negativa")
        replacement = None
        if (replaced_by or "").strip():
            if check_status != STATUS_REPLACED or len(selected) != 1:
                raise ValueError("'reemplazado por' solo aplica a un único árbol con estado reemplazado")
            replacement = trees_by_number.get(int(replaced_by)) if replaced_by.strip().isdigit() else None
            if replacement is None or replacement is selected[0]:
                raise ValueError("'reemplazado por' debe ser otro árbol de este proyecto")
        location = None
        if (visit_lat or "").strip() and (visit_lng or "").strip():
            try:
                lat, lng = float(visit_lat), float(visit_lng)
                accuracy = float(visit_accuracy) if (visit_accuracy or "").strip() else None
            except ValueError:
                raise ValueError("la ubicación del celular no es válida; volvé a tomarla")
            if not (-90 <= lat <= 90 and -180 <= lng <= 180):
                raise ValueError("la ubicación del celular no es válida; volvé a tomarla")
            location = (lat, lng, accuracy)
        if use_as_tree_location and (location is None or len(selected) != 1):
            raise ValueError("'usar como ubicación del árbol' necesita la ubicación y un solo árbol")
        uploads = [f for f in list(photos or []) + ([photo] if photo is not None else []) if f is not None and f.filename]
        if len(uploads) > MAX_VISIT_PHOTOS:
            raise ValueError(f"máximo {MAX_VISIT_PHOTOS} fotos por visita")
    except ValueError as e:
        return toast_redirect(url, f"No se guardó: {e}", error=True)

    # Each photo: upright, at most 1600 px, without EXIF (no GPS of the phone), uploaded once
    # and shared by every tree of this visit.
    saved_photos = []
    for upload in uploads:
        try:
            # photo_w/photo_h: never "height", which is the tree's height of this visit.
            contents, photo_w, photo_h = process_photo_sized(await upload.read(), upload.content_type,
                                                             upload.filename, max_side=VISIT_PHOTO_MAX_SIDE)
        except HTTPException as e:
            return toast_redirect(url, f"No se guardó: {e.detail}", error=True)
        photo_url = s3_service.upload_file(BytesIO(contents), "monitoreo.jpg", "image/jpeg")
        if not photo_url:
            return toast_redirect(url, "No se guardó: no se pudo subir la foto. Intentá de nuevo.", error=True)
        saved_photos.append((photo_url, photo_w, photo_h))

    daily_log = db.query(DailyLog).filter(
        DailyLog.project_id == project.id, DailyLog.user_id == user.id, DailyLog.date == day
    ).order_by(DailyLog.id.desc()).first()
    for tree in selected:
        record_check(tree, day, check_status, height_cm=height, notes=notes, public_comment=public_comment,
                     photos=saved_photos, location=location, use_as_tree_location=use_as_tree_location,
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
                "uid": t.id,  # stable id, for the tree card (/api/reforestation/trees/{uid}/visits)
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


@public_router.get("/trees/{tree_id}/visits")
def get_tree_visits(tree_id: int, db: Session = Depends(deps.get_db)):
    """The visits shown in the map's tree card: date, status and height; the public comment and
    the photos only for public projects. Never the internal note or who made the visit."""
    tree = db.get(ReforestationTree, tree_id)
    if tree is None or tree.project is None or tree.project.kind != KIND_INSTITUCIONAL:
        raise HTTPException(status_code=404, detail="Árbol no encontrado")
    return {"visits": public_visits(tree, absolute=False)}
