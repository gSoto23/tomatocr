from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Request
from sqlalchemy.orm import Session
from app.routers import deps
from app.db.models.reforestation import ReforestationProject, ReforestationTree
from app.core.templates import templates
from datetime import datetime
import csv
from io import StringIO

router = APIRouter(
    tags=["reforestation_admin"],
)

@router.get("/dashboard/reforestacion")
async def get_admin_dashboard(request: Request, db: Session = Depends(deps.get_db), current_user = Depends(deps.get_current_user)):
    if current_user.role != 'admin':
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
    if current_user.role != 'admin':
        raise HTTPException(status_code=403, detail="Not authorized")
        
    if not file.filename.endswith('.csv'):
        raise HTTPException(status_code=400, detail="Only CSV files are allowed.")
    
    content = await file.read()
    decoded = content.decode('utf-8')
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


public_router = APIRouter(prefix="/api/reforestation", tags=["reforestation_api"])

@public_router.get("/map-data")
async def get_map_data(db: Session = Depends(deps.get_db)):
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
