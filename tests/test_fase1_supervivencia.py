"""Fase 1: inventory upsert, monitoring, survival and the public map."""
from datetime import date
from io import BytesIO

import pytest

from app.db.models.log import DailyLog
from app.db.models.project import Project
from app.db.models.reforestation import ReforestationProject, ReforestationTree, TreeCheck
from app.utils.reforestation import add_months, parse_date, parse_tree_numbers, survival_summary
from tests.conftest import make_user, login, new_client

PLANTING = "TreeNumber,Species,Sector,Lat,Lng,Date\n" \
           "1,Guanacaste,Parque Norte,10.01,-84.21,2024-06-01\n" \
           "2,Cortez,Parque Norte,10.02,-84.22,2024-06-01\n" \
           "3,Roble,Parque Sur,10.03,-84.23,01/06/2024\n"


def upload(client, url, text, **data):
    return client.post(url, data=data, files={"file": ("datos.csv", text.encode("utf-8"), "text/csv")})


def trees_of(db, project):
    db.expire_all()
    return {t.tree_number: t for t in db.query(ReforestationTree).filter_by(project_id=project.id)}


@pytest.fixture
def admin(login_as, users):
    return login_as("admin")


@pytest.fixture
def planted(db, admin):
    response = upload(admin, "/dashboard/reforestacion/upload-csv", PLANTING, client_name="Municipalidad Alajuela")
    assert response.status_code == 200, response.text
    return db.query(ReforestationProject).filter_by(client_name="Municipalidad Alajuela").one()


# --- Parsing and the survival rule -----------------------------------------

def test_parse_tree_numbers():
    assert parse_tree_numbers("1-3, 7 10") == [1, 2, 3, 7, 10]
    assert parse_tree_numbers("5-3") == [3, 4, 5]
    for bad in ["", "a", "1-", "1-99999"]:
        with pytest.raises(ValueError):
            parse_tree_numbers(bad)


def test_parse_date_accepts_iso_and_costa_rica_format():
    assert parse_date("2026-09-26") == parse_date("26/09/2026") == date(2026, 9, 26)
    with pytest.raises(ValueError):
        parse_date("09-26-2026")


def test_add_months_handles_month_ends():
    assert add_months(date(2026, 8, 31), -6) == date(2026, 2, 28)
    assert add_months(date(2026, 1, 15), -12) == date(2025, 1, 15)


def tree(id, status, planted=date(2024, 6, 1), replaced_by_id=None):
    return ReforestationTree(id=id, tree_number=id, status=status, date_planted=planted, replaced_by_id=replaced_by_id)


def test_survival_rule():
    today = date(2026, 9, 27)
    trees = [
        tree(1, "vivo"), tree(2, "vivo"), tree(3, "vivo"),
        tree(4, "muerto"),
        tree(5, "reemplazado", replaced_by_id=9),
        tree(6, "sin_verificar"),
        tree(7, "vivo", planted=date(2026, 6, 1)),   # 4 months old: in no cohort
        tree(8, "vivo", planted=None),              # no date: in no cohort
        tree(9, "vivo", planted=date(2025, 1, 1)),  # replacement: counted apart
    ]
    s = survival_summary(trees, today)
    assert (s.planted, s.verified, s.alive, s.dead, s.replaced) == (8, 7, 5, 1, 1)
    assert s.replacements == 1 and s.without_date == 1
    c12 = s.cohorts[12]
    assert (c12.trees, c12.verified) == (6, 5)
    assert c12.survival_pct == 60.0      # 3 alive / (3 + 1 dead + 1 replaced)
    assert c12.verified_pct == 83.3     # 5 of 6
    assert s.cohorts[6].trees == 6


def test_survival_is_none_without_verified_trees():
    s = survival_summary([tree(1, "sin_verificar")], date(2026, 9, 27))
    assert s.cohorts[12].survival_pct is None
    assert s.cohorts[12].verified_pct == 0.0


# --- Inventory CSV: one format to download, complete and import again ------

UPLOAD_URL = "/dashboard/reforestacion/upload-csv"
HEADER = "TreeNumber,Species,Sector,Lat,Lng,Date,Status,CheckDate,HeightCm,Notes,ReplacedBy\n"


def import_csv(client, text, name="Municipalidad Alajuela"):
    return upload(client, UPLOAD_URL, text, client_name=name)


def test_reupload_updates_adds_and_never_deletes(db, admin, planted, users):
    trees = trees_of(db, planted)
    db.add(TreeCheck(tree_id=trees[3].id, checked_at=date(2026, 3, 1), status="vivo"))
    db.commit()

    csv2 = "TreeNumber,Species,Sector,Lat,Lng,Date\n" \
           "1,Guanacaste negro,Parque Norte,10.01,-84.21,2024-06-01\n" \
           "4,Cenízaro,Parque Este,10.04,-84.24,2026-06-01\n"
    response = import_csv(admin, csv2)
    assert response.status_code == 200
    assert "1 árboles nuevos, 1 actualizados" in response.json()["message"]
    assert "2 árboles registrados no venían en el archivo" in response.json()["message"]

    trees = trees_of(db, planted)
    assert sorted(trees) == [1, 2, 3, 4]
    assert trees[1].species == "Guanacaste negro"
    assert db.query(TreeCheck).count() == 1


def test_invalid_row_saves_nothing(db, admin, planted):
    bad = HEADER + \
          "10,Roble,Sur,10.1,-84.1,2026-01-01,,,,,\n" \
          "abc,Roble,Sur,10.1,-84.1,2026-01-01,,,,,\n" \
          "11,Roble,Sur,10.1,-84.1,2026-13-45,,,,,\n" \
          "10,Roble,Sur,10.1,-84.1,2026-01-01,,,,,\n" \
          "1,,,,,,enfermo,2026-09-01,,,\n" \
          "2,,,,,,vivo,,,,\n" \
          "3,,,,,,,,,nota sin estado,\n"
    response = import_csv(admin, bad)
    assert response.status_code == 400
    detail = response.json()["detail"]
    for line in range(3, 9):
        assert f"Línea {line}" in detail
    assert sorted(trees_of(db, planted)) == [1, 2, 3]
    assert db.query(TreeCheck).count() == 0


def test_only_tree_number_is_required(db, admin, planted):
    response = import_csv(admin, HEADER + "50,,,,,,,,,,\n")
    assert response.status_code == 200, response.text
    tree = trees_of(db, planted)[50]
    assert (tree.species, tree.lat, tree.date_planted, tree.status) == (None, None, None, "sin_verificar")


def test_empty_cells_never_erase_stored_data(db, admin, planted):
    import_csv(admin, HEADER + "1,,,,,,vivo,2026-09-01,120,Buen estado,\n")
    trees = trees_of(db, planted)
    assert (trees[1].species, trees[1].sector_name, trees[1].lat) == ("Guanacaste", "Parque Norte", 10.01)
    assert trees[1].status == "vivo" and trees[1].checks[0].height_cm == 120


def test_monitoring_columns_record_checks(db, admin, planted):
    csv_text = HEADER + \
        '1,,,,,,vivo,2026-09-01,"120,5",Buen estado,\n' \
        "2,,,,,,Muerto,26/09/2026,,Seco,\n" \
        "3,,,,,,reemplazado,2026-09-01,,,4\n" \
        "4,Roble,Parque Sur,10.05,-84.25,2026-09-01,,,,,\n"
    response = import_csv(admin, csv_text)
    assert response.status_code == 200, response.text
    assert "3 monitoreos nuevos" in response.json()["message"]
    trees = trees_of(db, planted)
    assert trees[1].status == "vivo" and trees[1].checks[0].height_cm == 120.5
    assert trees[2].status == "muerto" and trees[2].last_checked_at == date(2026, 9, 26)
    assert trees[3].status == "reemplazado" and trees[3].replaced_by_id == trees[4].id


def test_download_has_every_column_and_blanks(db, admin, planted):
    import_csv(admin, HEADER + "1,,,,,,vivo,2026-09-01,85,Sano,\n3,,,,,,reemplazado,2026-09-02,,,2\n")
    import_csv(admin, HEADER + "60,,,,,,,,,,\n")
    lines = admin.get(f"/dashboard/reforestacion/download-csv/{planted.id}").text.splitlines()
    assert lines[0] == HEADER.strip()
    assert lines[1] == "1,Guanacaste,Parque Norte,10.01,-84.21,2024-06-01,vivo,2026-09-01,85,Sano,"
    assert lines[2] == "2,Cortez,Parque Norte,10.02,-84.22,2024-06-01,,,,,"
    assert lines[3] == "3,Roble,Parque Sur,10.03,-84.23,2024-06-01,reemplazado,2026-09-02,,,2"
    assert lines[4] == "60,,,,,,,,,,"


def test_reimporting_the_download_changes_nothing(db, admin, planted):
    import_csv(admin, HEADER + "1,,,,,,vivo,2026-09-01,85,Sano,\n2,,,,,,muerto,2026-09-01,,,\n")
    downloaded = admin.get(f"/dashboard/reforestacion/download-csv/{planted.id}").text
    response = import_csv(admin, downloaded)
    assert response.status_code == 200, response.text
    assert "monitoreos" not in response.json()["message"]
    assert db.query(TreeCheck).count() == 2
    assert admin.get(f"/dashboard/reforestacion/download-csv/{planted.id}").text == downloaded


def test_edit_the_download_and_import_it_again(db, admin, planted):
    import_csv(admin, HEADER + "1,,,,,,vivo,2026-09-01,85,,\n")
    lines = admin.get(f"/dashboard/reforestacion/download-csv/{planted.id}").text.splitlines()
    lines[1] = "1,Guanacaste,Parque Norte,10.01,-84.21,2024-06-01,muerto,2026-09-01,85,Corregido,"  # same date: fix
    lines[2] = "2,Cortez,Parque Norte,10.02,-84.22,2024-06-01,vivo,2026-09-20,40,,"            # new check
    response = import_csv(admin, "\n".join(lines) + "\n")
    assert "1 monitoreos nuevos y 1 corregidos" in response.json()["message"]
    trees = trees_of(db, planted)
    assert trees[1].status == "muerto" and len(trees[1].checks) == 1 and trees[1].checks[0].notes == "Corregido"
    assert trees[2].status == "vivo"


def test_older_check_does_not_override_latest_status(db, admin, planted):
    import_csv(admin, HEADER + "1,,,,,,muerto,2026-09-01,,,\n")
    import_csv(admin, HEADER + "1,,,,,,vivo,2026-03-01,,,\n")
    t = trees_of(db, planted)[1]
    assert t.status == "muerto" and t.last_checked_at == date(2026, 9, 1)
    assert len(t.checks) == 2


def test_future_check_date_is_rejected(db, admin, planted):
    response = import_csv(admin, HEADER + "1,,,,,,vivo,2999-01-01,,,\n")
    assert response.status_code == 400 and "futura" in response.json()["detail"]


def test_file_needs_tree_number_column(admin, planted):
    response = import_csv(admin, "Species,Status\nRoble,vivo\n")
    assert response.status_code == 400 and "TreeNumber" in response.json()["detail"]


def test_template_has_every_column(admin):
    response = admin.get("/dashboard/reforestacion/plantilla-csv")
    assert response.status_code == 200
    assert response.text.splitlines()[0] == HEADER.strip()


# --- Settings ------------------------------------------------------------------

def test_settings_link_and_authorization(db, admin, planted, users):
    response = admin.post(f"/dashboard/reforestacion/{planted.id}/settings", data={
        "linked_project_id": str(users["project_id"]),
        "is_public": "true", "public_name": "Municipalidad de Alajuela", "consent_date": "2026-09-27",
    }, follow_redirects=False)
    assert response.status_code == 303
    db.refresh(planted)
    assert planted.project_id == users["project_id"] and planted.is_public
    assert planted.consent_date == date(2026, 9, 27)


def test_settings_reject_authorization_without_name(db, admin, planted):
    admin.post(f"/dashboard/reforestacion/{planted.id}/settings",
               data={"is_public": "true", "public_name": ""})
    db.refresh(planted)
    assert planted.is_public is False


@pytest.mark.parametrize("role", ["supervisor", "worker", "client", "ventas"])
def test_only_admin_manages_reforestation(role, login_as, planted):
    client = login_as(role)
    assert client.post(f"/dashboard/reforestacion/{planted.id}/settings", data={"public_name": "X"}).status_code == 403
    assert import_csv(client, HEADER + "1,,,,,,vivo,2026-09-01,,,\n").status_code == 403
    assert client.get(f"/dashboard/reforestacion/download-csv/{planted.id}").status_code == 403


# --- Field monitoring ------------------------------------------------------------

@pytest.fixture
def linked(db, planted, users):
    planted.project_id = users["project_id"]
    db.commit()
    return planted


@pytest.mark.parametrize("role,expected", [
    ("admin", 200), ("supervisor", 200), ("worker", 200), ("client", 403), ("ventas", 403),
])
def test_monitoring_page_access(role, expected, login_as, linked, users):
    response = login_as(role).get(f"/projects/{users['project_id']}/monitoreo", follow_redirects=False)
    assert response.status_code == expected


def test_unassigned_worker_cannot_monitor(db, linked, users):
    make_user(db, "otro_worker", "worker")
    client = new_client()
    login(client, "otro_worker")
    assert client.get(f"/projects/{users['project_id']}/monitoreo").status_code == 403


def test_monitoring_page_needs_linked_trees(login_as, planted, users):
    assert login_as("admin").get(f"/projects/{users['project_id']}/monitoreo").status_code == 404


def test_project_page_shows_monitoring_link_only_when_linked(login_as, planted, db, users):
    admin = login_as("admin")
    assert "/monitoreo" not in admin.get(f"/projects/{users['project_id']}").text
    planted.project_id = users["project_id"]
    db.commit()
    assert f"/projects/{users['project_id']}/monitoreo" in admin.get(f"/projects/{users['project_id']}").text
    assert "/monitoreo" not in login_as("client").get(f"/projects/{users['project_id']}").text


def post_monitoring(client, project_id, **data):
    form = {"checked_at": date.today().isoformat(), "mode": "numbers", "status": "vivo"}
    form.update(data)
    files = form.pop("files", None)
    return client.post(f"/projects/{project_id}/monitoreo", data=form, files=files, follow_redirects=False)


def test_worker_records_by_numbers_and_links_the_daily_log(db, login_as, linked, users):
    log = DailyLog(project_id=users["project_id"], user_id=users["worker"].id, date=date.today())
    db.add(log)
    db.commit()
    response = post_monitoring(login_as("worker"), users["project_id"], tree_numbers="1-2", height_cm="85")
    assert response.status_code == 303
    # Cookie values with accents travel octal-escaped; base_dashboard.html decodes them.
    assert "Monitoreo guardado: 2 \\341rboles marcados como vivo" in response.headers["set-cookie"]
    checks = db.query(TreeCheck).all()
    assert len(checks) == 2
    assert {c.daily_log_id for c in checks} == {log.id}
    assert {c.user_id for c in checks} == {users["worker"].id}


def test_record_whole_sector(db, login_as, linked, users):
    post_monitoring(login_as("supervisor"), users["project_id"], mode="sector", sector="Parque Norte", status="muerto")
    trees = trees_of(db, linked)
    assert trees[1].status == trees[2].status == "muerto"
    assert trees[3].status == "sin_verificar"


def test_unknown_numbers_save_nothing(db, login_as, linked, users):
    response = post_monitoring(login_as("admin"), users["project_id"], tree_numbers="1, 50")
    assert "toast_type=error" in response.headers["set-cookie"] or response.cookies.get("toast_type") == "error"
    assert db.query(TreeCheck).count() == 0


def test_future_date_is_rejected(db, login_as, linked, users):
    post_monitoring(login_as("admin"), users["project_id"], tree_numbers="1", checked_at="2999-01-01")
    assert db.query(TreeCheck).count() == 0


def jpeg_bytes():
    from PIL import Image
    buffer = BytesIO()
    Image.new("RGB", (40, 30), (30, 120, 60)).save(buffer, "JPEG")
    return buffer.getvalue()


def test_photo_is_validated_and_stored(db, login_as, linked, users, monkeypatch):
    from app.routers import reforestation
    monkeypatch.setattr(reforestation.s3_service, "upload_file", lambda f, name, ct: f"https://s3/{name}")
    admin = login_as("admin")

    post_monitoring(admin, users["project_id"], tree_numbers="1",
                    files={"photo": ("foto.exe", b"MZ", "application/octet-stream")})
    assert db.query(TreeCheck).count() == 0

    post_monitoring(admin, users["project_id"], tree_numbers="1",
                    files={"photo": ("foto.jpg", BytesIO(jpeg_bytes()), "image/jpeg")})
    assert db.query(TreeCheck).one().photo_path == "https://s3/monitoreo.jpg"


# --- Public map ----------------------------------------------------------------------

def test_map_shows_only_institutional_projects_and_authorized_names(db, admin, planted):
    public = ReforestationProject(client_name="Otro municipio", kind="institucional")
    private = ReforestationProject(client_name="Empresa X", kind="darboles", is_public=True, public_name="Empresa X")
    for p, n in [(public, 100), (private, 200)]:
        p.trees = [ReforestationTree(tree_number=n, species="Roble", sector_name="S", lat=10, lng=-84,
                                     date_planted=date(2024, 1, 1))]
        db.add(p)
    planted.is_public, planted.public_name = True, "Municipalidad de Alajuela"
    db.commit()
    import_csv(admin, HEADER + "1,,,,,,vivo,2026-09-01,,nota interna,\n2,,,,,,muerto,2026-09-01,,,\n"
               "99,,,,,,,,,,\n")  # no coordinates yet: not on the map

    data = new_client().get("/api/reforestation/map-data").json()
    names = {t["project"] for t in data["trees"]}
    assert names == {"Municipalidad de Alajuela", "Proyecto institucional"}
    assert "Empresa X" not in str(data) and "Otro municipio" not in str(data)
    assert "nota interna" not in str(data)
    assert set(data["trees"][0]) == {"id", "project", "sector", "species", "lat", "lng", "date", "status"}

    assert 99 not in {t["id"] for t in data["trees"]}
    summary = next(p for p in data["projects"] if p["project"] == "Municipalidad de Alajuela")
    assert summary == {"project": "Municipalidad de Alajuela", "planted": 4, "survival_12m": 50.0,
                       "verified_12m": 66.7, "last_check": "2026-09-01"}


def test_settings_form_has_no_project_type(db, admin, planted):
    # darboles.com is an independent platform: every project here is institutional.
    html = admin.get("/dashboard/reforestacion").text
    assert 'name="kind"' not in html and "Dárboles (comercial" not in html
    admin.post(f"/dashboard/reforestacion/{planted.id}/settings", data={"public_name": "Municipalidad de Alajuela"})
    db.refresh(planted)
    assert planted.kind == "institucional"
