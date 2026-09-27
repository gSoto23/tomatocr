from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from app.routers import deps
from app.core.roles import ADMIN
from app.db.models.reforestation import ReforestationProject, ReforestationTree
from app.core.templates import templates
from datetime import datetime
import csv
import re
import unicodedata
from io import StringIO
from urllib.parse import quote

router = APIRouter(
    tags=["reforestation_admin"],
)

@router.get("/dashboard/reforestacion")
def get_admin_dashboard(request: Request, db: Session = Depends(deps.get_db), current_user = Depends(deps.get_current_user)):
    if current_user.role != ADMIN:
        raise HTTPException(status_code=403, detail="Not authorized")
    projects = db.query(ReforestationProject).all()
    return templates.TemplateResponse("reforestation/admin.html", {"request": request, "user": current_user, "projects": projects})

@router.post("/dashboard/reforestacion/upload-csv")
async def upload_csv(
    client_name: str = Form(...),
    file: UploadFile = File(...),
    db: Session = Depends(deps.get_db),
    current_user = Depends(deps.get_current_user)
):
    if current_user.role != ADMIN:
        raise HTTPException(status_code=403, detail="Not authorized")
        
    if not file.filename.endswith('.csv'):
        raise HTTPException(status_code=400, detail="Only CSV files are allowed.")
    
    content = await file.read()
    try:
        decoded = content.decode('utf-8-sig')  # Handle BOM if present
    except UnicodeDecodeError:
        try:
            decoded = content.decode('cp1252')  # Excel on Windows (most common source of broken tildes/ñ)
        except UnicodeDecodeError:
            decoded = content.decode('latin-1', errors='replace')  # Last resort, never raises
        
    csv_reader = csv.DictReader(StringIO(decoded))
    
    required_cols = {"TreeNumber", "Species", "Sector", "Lat", "Lng"}
    if not required_cols.issubset(set(csv_reader.fieldnames)):
        raise HTTPException(status_code=400, detail=f"CSV must contain columns: {', '.join(required_cols)}")
    
    project = db.query(ReforestationProject).filter(ReforestationProject.client_name == client_name).first()
    if not project:
        project = ReforestationProject(client_name=client_name)
        db.add(project)
        db.commit()
        db.refresh(project)
    else:
        db.query(ReforestationTree).filter(ReforestationTree.project_id == project.id).delete()
        db.commit()

    trees_to_add = []
    for row in csv_reader:
        try:
            tree_num = int(row["TreeNumber"])
            lat = float(row["Lat"])
            lng = float(row["Lng"])
            
            date_planted = None
            if "Date" in row and row["Date"]:
                try:
                    date_planted = datetime.strptime(row["Date"], "%Y-%m-%d").date()
                except ValueError:
                    pass

            trees_to_add.append(ReforestationTree(
                project_id=project.id,
                tree_number=tree_num,
                species=row["Species"],
                sector_name=row["Sector"],
                lat=lat,
                lng=lng,
                date_planted=date_planted
            ))
        except (ValueError, KeyError) as e:
            continue

    if trees_to_add:
        db.bulk_save_objects(trees_to_add)
        db.commit()

    return {"message": f"Successfully imported {len(trees_to_add)} trees for client {client_name}."}


@router.get("/dashboard/reforestacion/download-csv/{project_id}")
def download_csv(
    project_id: int, 
    db: Session = Depends(deps.get_db), 
    current_user = Depends(deps.get_current_user)
):
    if current_user.role != ADMIN:
        raise HTTPException(status_code=403, detail="Not authorized")
        
    project = db.query(ReforestationProject).filter(ReforestationProject.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
        
    output = StringIO()
    writer = csv.writer(output)
    writer.writerow(["TreeNumber", "Species", "Sector", "Lat", "Lng", "Date"])
    
    for tree in project.trees:
        writer.writerow([
            tree.tree_number, 
            tree.species, 
            tree.sector_name, 
            tree.lat, 
            tree.lng, 
            tree.date_planted.strftime("%Y-%m-%d") if tree.date_planted else ""
        ])
        
    output.seek(0)
    filename = f"{(project.client_name or 'proyecto').replace(' ', '_')}_inventario.csv"
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": content_disposition(filename)}
    )


def content_disposition(filename: str) -> str:
    """Attachment header that survives non-ASCII names (RFC 6266 / RFC 5987).

    HTTP headers are latin-1, so a name like "Árbol" can't go in `filename`
    as-is: that gets an ASCII fallback, and browsers use `filename*` instead.
    """
    ascii_name = unicodedata.normalize("NFKD", filename).encode("ascii", "ignore").decode("ascii")
    ascii_name = re.sub(r'[^A-Za-z0-9._-]', "_", ascii_name) or "inventario.csv"
    return f"attachment; filename=\"{ascii_name}\"; filename*=UTF-8''{quote(filename, safe='')}"


public_router = APIRouter(prefix="/api/reforestation", tags=["reforestation_api"])

@public_router.get("/map-data")
def get_map_data(db: Session = Depends(deps.get_db)):
    trees = db.query(ReforestationTree).all()
    result = []
    for t in trees:
        client_name = t.project.client_name if t.project else "Unknown"
        result.append({
            "id": t.tree_number,
            "project": client_name,
            "sector": t.sector_name,
            "species": t.species,
            "lat": t.lat,
            "lng": t.lng,
            "date": t.date_planted.strftime("%Y-%m-%d") if t.date_planted else "N/A"
        })
    return {"trees": result}
