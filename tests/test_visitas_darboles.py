"""Tree visits with several photos, a public comment and GPS; the map's tree card; the read-only
sync for darboles.com; and the repair of names broken by a Mac Roman inventory."""
from datetime import date, datetime, timedelta
from io import BytesIO

import pytest
from PIL import Image

from app.core.config import settings
from app.db.models.reforestation import (LOCATION_TREE, ReforestationProject, ReforestationTree, TreeCheck,
                                         TreeCheckPhoto)
from app.routers import reforestation as reforestation_router
from app.utils.reforestation import decode_text, public_visits, record_check, repair_mojibake
from tests.conftest import new_client
from tests.test_fase1_supervivencia import PLANTING, linked, planted, post_monitoring, upload  # noqa: F401

KEY = "clave-de-sincronizacion-de-prueba"


@pytest.fixture
def admin(login_as, users):
    return login_as("admin")


@pytest.fixture
def s3(monkeypatch):
    uploaded = []

    def fake_upload(f, name, content_type):
        uploaded.append(f.read())
        return f"https://s3/{len(uploaded)}-{name}"
    monkeypatch.setattr(reforestation_router.s3_service, "upload_file", fake_upload)
    return uploaded


def jpeg_with_gps(size=(3000, 2000)) -> bytes:
    image = Image.new("RGB", size, (30, 120, 60))
    exif = Image.Exif()
    exif[0x010F] = "Camara de prueba"  # Make
    gps = exif.get_ifd(0x8825)  # GPSInfo
    gps[1], gps[2] = "N", (10.0, 0.0, 30.0)
    out = BytesIO()
    image.save(out, "JPEG", exif=exif.tobytes())
    return out.getvalue()


def trees(db, project):
    db.expire_all()
    return {t.tree_number: t for t in db.query(ReforestationTree).filter_by(project_id=project.id)}


def make_public(db, project, public=True):
    project.is_public, project.public_name = public, ("Municipalidad de Alajuela" if public else None)
    db.commit()


# --- Monitoring form ---------------------------------------------------------------

def test_visit_with_photos_comment_and_gps(db, admin, linked, users, s3):
    files = [("photos", (f"foto{i}.jpg", BytesIO(jpeg_with_gps()), "image/jpeg")) for i in range(2)]
    response = post_monitoring(admin, users["project_id"], tree_numbers="1", notes="Revisar riego", height_cm="85",
                               public_comment="Buen crecimiento", visit_lat="10.0035", visit_lng="-84.2441",
                               visit_accuracy="6", use_as_tree_location="true", files=files)
    assert response.status_code == 303 and db.query(TreeCheck).count() == 1
    check = db.query(TreeCheck).one()
    assert (check.notes, check.public_comment, check.lat, check.lng, check.accuracy_m) == \
        ("Revisar riego", "Buen crecimiento", 10.0035, -84.2441, 6.0)
    assert check.height_cm == 85  # not the photo's height in pixels
    assert [p.width for p in check.photos] == [1600, 1600] and check.photos[0].height == 1067
    tree = trees(db, linked)[1]
    assert (tree.lat, tree.lng, tree.location_source) == (10.0035, -84.2441, LOCATION_TREE)
    assert trees(db, linked)[2].location_source == "sector"


def test_photos_lose_exif(s3, admin, linked, users):
    post_monitoring(admin, users["project_id"], tree_numbers="1",
                    files=[("photos", ("foto.jpg", BytesIO(jpeg_with_gps()), "image/jpeg"))])
    stored = Image.open(BytesIO(s3[0]))
    assert not stored.getexif() and "exif" not in stored.info


def test_location_for_the_tree_needs_one_tree_and_a_reading(db, admin, linked, users, s3):
    post_monitoring(admin, users["project_id"], tree_numbers="1-2", visit_lat="10", visit_lng="-84",
                    use_as_tree_location="true")
    post_monitoring(admin, users["project_id"], tree_numbers="1", use_as_tree_location="true")
    post_monitoring(admin, users["project_id"], tree_numbers="1", visit_lat="200", visit_lng="-84")
    assert db.query(TreeCheck).count() == 0


def test_at_most_six_photos(db, admin, linked, users, s3):
    files = [("photos", (f"f{i}.jpg", BytesIO(jpeg_with_gps((40, 30))), "image/jpeg")) for i in range(7)]
    post_monitoring(admin, users["project_id"], tree_numbers="1", files=files)
    assert db.query(TreeCheck).count() == 0 and s3 == []


def test_form_says_what_is_public(admin, linked, users, db):
    html = admin.get(f"/projects/{users['project_id']}/monitoreo").text
    assert "Nota interna (no se publica)" in html and "Comentario público" in html
    assert "no se publican" in html  # the project hasn't authorized its name yet
    make_public(db, linked)
    assert "Se ve en la ficha del árbol en el mapa y en darboles.com" in admin.get(f"/projects/{users['project_id']}/monitoreo").text


# --- Map tree card --------------------------------------------------------------------

def visit(db, tree, **extra):
    check = record_check(tree, date.today(), "vivo", height_cm=80, notes="interna", public_comment="Se ve bien",
                         photos=[("https://s3/a.jpg", 1600, 1200)], **extra)
    db.commit()
    return check


def test_tree_card_shows_visits_only_what_is_public(db, linked):
    tree = trees(db, linked)[1]
    empty = new_client().get(f"/api/reforestation/trees/{trees(db, linked)[2].id}/visits").json()
    assert empty == {"visits": []}  # no visits: the card shows nothing more
    visit(db, tree)
    data = new_client().get(f"/api/reforestation/trees/{tree.id}/visits").json()["visits"][0]
    assert data["height_cm"] == 80 and data["public_comment"] is None and data["photos"] == []  # not public
    make_public(db, linked)
    data = new_client().get(f"/api/reforestation/trees/{tree.id}/visits").json()["visits"][0]
    assert data["public_comment"] == "Se ve bien" and data["photos"][0]["url"] == "https://s3/a.jpg"
    assert "interna" not in str(data) and "user" not in data
    map_tree = next(t for t in new_client().get("/api/reforestation/map-data").json()["trees"] if t["id"] == 1)
    assert map_tree["uid"] == tree.id


def test_old_single_photo_still_shows(db, linked):
    make_public(db, linked)
    tree = trees(db, linked)[1]
    record_check(tree, date.today(), "vivo", photo_path="/static/uploads/vieja.jpg")
    db.commit()
    assert public_visits(tree)[0]["photos"] == [{"url": "https://tomatocr.com/static/uploads/vieja.jpg",
                                                 "width": None, "height": None}]


# --- darboles.com sync -------------------------------------------------------------------

@pytest.fixture
def sync_key(monkeypatch):
    monkeypatch.setattr(settings, "DARBOLES_SYNC_API_KEY", KEY)


def sync(params=None, key=KEY):
    return new_client().get("/api/darboles/trees", params=params or {}, headers={"X-API-Key": key} if key else {})


def test_sync_needs_its_key(monkeypatch, linked):
    monkeypatch.setattr(settings, "DARBOLES_SYNC_API_KEY", "")
    assert sync().status_code == 503
    monkeypatch.setattr(settings, "DARBOLES_SYNC_API_KEY", KEY)
    assert sync(key="otra").status_code == 401 and sync(key=None).status_code == 401
    monkeypatch.setattr(settings, "DARBOLES_API_KEY", "clave-de-prospectos")
    assert sync(key="clave-de-prospectos").status_code == 401  # the leads key doesn't open it
    assert sync().status_code == 200


def test_sync_contract_and_privacy(db, sync_key, linked):
    tree = trees(db, linked)[1]
    visit(db, tree, location=(10.1, -84.1, 5), use_as_tree_location=True)
    body = sync().json()
    assert body["generated_at"].endswith("Z") and body["next_cursor"] is None and len(body["trees"]) == 3
    first = body["trees"][0]
    assert set(first) == {"id", "project", "tree_number", "species", "sector", "lat", "lng", "location_precision",
                          "date_planted", "status", "last_checked_at", "replaced_by_id", "updated_at", "visits"}
    assert first["project"] == {"id": linked.id, "name": "Proyecto institucional", "public": False}
    assert first["location_precision"] == "tree" and first["visits"][0]["photos"] == []
    assert first["visits"][0]["public_comment"] is None
    text = str(body)
    assert "interna" not in text and "Municipalidad Alajuela" not in text  # never notes or client_name
    make_public(db, linked)
    first = sync().json()["trees"][0]
    assert first["project"]["name"] == "Municipalidad de Alajuela" and first["project"]["public"] is True
    assert first["visits"][0]["public_comment"] == "Se ve bien" and first["visits"][0]["photos"][0]["width"] == 1600
    assert sync().json()["trees"][1]["location_precision"] == "sector"


def test_sync_pages_and_updated_since(db, sync_key, linked):
    page1 = sync({"limit": 2}).json()
    assert len(page1["trees"]) == 2 and page1["next_cursor"]
    page2 = sync({"limit": 2, "cursor": page1["next_cursor"]}).json()
    assert [t["tree_number"] for t in page2["trees"]] == [3] and page2["next_cursor"] is None
    assert sync({"limit": 1001}).status_code == 422 and sync({"cursor": "x"}).status_code == 400
    later = (datetime.utcnow() + timedelta(minutes=1)).isoformat() + "Z"
    assert sync({"updated_since": later}).json()["trees"] == []
    for number, tree in trees(db, linked).items():
        tree.updated_at = datetime(2026, 6, 1) if number == 2 else datetime(2026, 1, 1)
    db.commit()
    assert [t["tree_number"] for t in sync({"updated_since": "2026-03-01T00:00:00Z"}).json()["trees"]] == [2]
    assert sync({"updated_since": "ayer"}).status_code == 400


def test_changing_the_authorization_touches_the_trees(db, admin, linked):
    before = trees(db, linked)[1].updated_at
    admin.post(f"/dashboard/reforestacion/{linked.id}/settings", data={"is_public": "true", "public_name": "Muni"})
    assert trees(db, linked)[1].updated_at > before


# --- Encoding --------------------------------------------------------------------------

NAMES = ["Almendro de montaña", "Guachipelín", "Targuá", "Parque Próspero Fernández", "Parque Juan Santamaría"]


def test_importer_reads_mac_roman_windows_and_utf8():
    for name in NAMES:
        assert decode_text(f"TreeNumber,Species\n1,{name}\n".encode("mac_roman")).endswith(f"{name}\n")
        assert decode_text(name.encode("cp1252")) == name
        assert decode_text(name.encode("utf-8")) == name


def test_mac_roman_csv_imports_with_accents(db, admin):
    text = "TreeNumber,Species,Sector,Lat,Lng,Date\n1,Guachipelín,Parque Próspero Fernández,10,-84,2024-06-01\n"
    admin.post("/dashboard/reforestacion/upload-csv", data={"client_name": "Muni Mac"},
               files={"file": ("mac.csv", text.encode("mac_roman"), "text/csv")})
    tree = db.query(ReforestationTree).one()
    assert (tree.species, tree.sector_name) == ("Guachipelín", "Parque Próspero Fernández")


def test_repair_script_fixes_and_unifies(db, admin):
    from scripts.reparar_codificacion import plan
    project = ReforestationProject(client_name="Municipalidad de Alajuela")
    db.add(project)
    db.flush()
    broken = [name.encode("mac_roman").decode("latin-1") for name in NAMES]
    db.add_all([ReforestationTree(project_id=project.id, tree_number=1, species=broken[1], sector_name=broken[3]),
                ReforestationTree(project_id=project.id, tree_number=2, species="Guachipelin", sector_name=broken[4]),
                ReforestationTree(project_id=project.id, tree_number=3, species=broken[0], sector_name="Parque Lisboa")])
    db.commit()
    assert repair_mojibake(broken[2]) == "Targuá" and repair_mojibake("Cedro") == "Cedro"
    changes, summary = plan(db)
    new = {(type(o).__name__, o.tree_number if hasattr(o, "tree_number") else None, f): v for o, f, _, v in changes}
    assert new[("ReforestationTree", 1, "species")] == "Guachipelín"
    assert new[("ReforestationTree", 2, "species")] == "Guachipelín"  # the spelling without accent is unified
    assert new[("ReforestationTree", 1, "sector_name")] == "Parque Próspero Fernández"
    assert new[("ReforestationTree", 3, "species")] == "Almendro de montaña"
    assert db.query(ReforestationTree).filter_by(tree_number=1).one().species == broken[1]  # dry run: nothing saved


def test_big_groups_open_as_a_list():
    html = new_client().get("/proyectos-reforestacion").text
    assert "listThreshold: 30" in html and "openList(cluster)" in html and "zoomToBoundsOnClick: false" in html
    assert "Volver a la lista" in html and "Buscar número, especie o sector" in html
