"""UX round 2a (docs/PUNTOS_DIFICILES_UX.md, priority B): login messages, page titles,
the admin dashboard, the supervisor's projects, editing a report, the project form,
the quote tool, employee documents and the activity log."""
from datetime import date, timedelta
from io import BytesIO

import pytest
from PIL import Image

from app.db.models.activity import ActivityLog
from app.db.models.finance import BudgetLine, Invoice, InvoiceStatus, ProjectBudget
from app.db.models.log import DailyLog, Photo
from app.db.models.project import Project
from app.db.models.project_details import ProjectTask
from app.db.models.quote import Quote
from app.db.models.user import User
from app.db.models.user_document import UserDocument
from tests.conftest import new_client

# --- Access and titles --------------------------------------------------------------------


def test_home_offers_login_on_phone_and_tablet():
    html = new_client().get("/").text
    assert 'id="loginMenuBtn"' in html and "Tu usuario está desactivado" in html
    assert "/static/css/tailwind.css?v=" in html and "/static/js/script.js?v=" in html


@pytest.mark.parametrize("path,title", [("/projects", "Proyectos"), ("/logs", "Bitácora"), ("/users", "Empleados"),
                                        ("/calendar", "Calendario"), ("/payroll", "Planilla")])
def test_top_bar_names_the_module(login_as, path, title):
    html = login_as("admin").get(path).text
    bar = html.split('<header', 1)[1].split('</header>', 1)[0]
    assert title in bar and "Dashboard" not in bar.replace('href="/dashboard"', "")


def test_only_admin_sees_new_project(login_as):
    assert "Nuevo Proyecto" in login_as("admin").get("/projects").text
    for role in ("supervisor", "worker"):
        assert "Nuevo Proyecto" not in login_as(role).get("/projects").text


# --- Admin dashboard ------------------------------------------------------------------------

@pytest.fixture
def invoices(db, users):
    budget = ProjectBudget(project_id=users["project_id"])
    db.add(budget)
    db.flush()
    line = BudgetLine(budget_id=budget.id, name="Mantenimiento", subtotal=1000)
    db.add(line)
    db.flush()
    late = Invoice(budget_id=budget.id, budget_line_id=line.id, invoice_number="FE-1", amount=100, issue_date=date.today() - timedelta(days=40),
                   due_date=date.today() - timedelta(days=10), status=InvoiceStatus.PENDING)
    paid = Invoice(budget_id=budget.id, budget_line_id=line.id, invoice_number="FE-2", amount=50, issue_date=date.today(),
                   due_date=date.today() + timedelta(days=30), status=InvoiceStatus.PAID)
    db.add_all([late, paid])
    db.commit()
    return late, paid


def test_dashboard_marks_overdue_and_explains_the_list(db, login_as, invoices):
    late, _ = invoices
    html = login_as("admin").get("/dashboard").text
    db.expire_all()
    assert db.get(Invoice, late.id).status == InvoiceStatus.OVERDUE
    assert "Facturas por cobrar" in html and "FE-1" in html and "FE-2" not in html
    assert "showFilters: false" in html


def test_dashboard_filters_open_and_say_what_they_change(login_as, invoices):
    html = login_as("admin").get("/dashboard?invoice_status=pagada").text
    assert "showFilters: true" in html and "según filtros" in html and "FE-2" in html
    assert "Facturas según los filtros" in html


# --- Supervisor and projects ----------------------------------------------------------------

@pytest.fixture
def other_project(db):
    project = Project(name="Proyecto ajeno", is_active=True)
    db.add(project)
    db.commit()
    return project


def test_supervisor_sees_and_reports_on_any_project(db, login_as, users, other_project):
    client = login_as("supervisor")
    assert "Proyecto ajeno" in client.get("/projects").text
    assert "Proyecto ajeno" in client.get("/logs/new").text
    response = client.post("/logs/new", data={"project_id": other_project.id, "date": date.today().isoformat(),
                                              "notes": "ok"}, follow_redirects=False)
    assert response.status_code == 303
    log = db.query(DailyLog).filter(DailyLog.project_id == other_project.id).one()
    assert client.get(f"/logs/{log.id}/detail").status_code == 200
    assert client.get(f"/logs/?project_id={other_project.id}").status_code == 200


def test_worker_filter_on_foreign_project_is_friendly(login_as, other_project):
    client = login_as("worker")
    assert "Proyecto ajeno" not in client.get("/logs/").text
    response = client.get(f"/logs/?project_id={other_project.id}", follow_redirects=False)
    assert response.status_code == 303 and response.headers["location"] == "/logs"


# --- Editing a report -----------------------------------------------------------------------

def jpeg():
    buffer = BytesIO()
    Image.new("RGB", (40, 30), (10, 90, 30)).save(buffer, "JPEG")
    return buffer.getvalue()


@pytest.fixture
def report(db, users):
    task = ProjectTask(project_id=users["project_id"], description="Corta", is_required=True)
    db.add(task)
    db.flush()
    log = DailyLog(project_id=users["project_id"], user_id=users["worker"].id, date=date.today(), notes="ok")
    db.add(log)
    db.flush()
    photo = Photo(log_id=log.id, file_path="/static/uploads/vieja.jpg")
    db.add(photo)
    db.commit()
    return {"log": log, "task": task, "photo": photo}


def test_new_report_requires_the_required_tasks(login_as, users, report):
    response = login_as("worker").post("/logs/new", data={"project_id": users["project_id"],
                                                          "date": date.today().isoformat(), "notes": "x"})
    assert response.status_code == 400 and "Corta" in response.json()["detail"]


def test_edit_report_checks_tasks_allows_empty_notes_and_changes_photos(db, login_as, report, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "app" / "static" / "uploads").mkdir(parents=True)
    client = login_as("worker")
    url = f"/logs/{report['log'].id}/edit"
    missing = client.post(url, data={"notes": "x"})
    assert missing.status_code == 400 and "Corta" in missing.json()["detail"]
    done = client.post(url, data={"notes": "", "tasks": [report["task"].id], "remove_photos": [report["photo"].id]},
                       files=[("photos", ("nueva.jpg", jpeg(), "image/jpeg"))], follow_redirects=False)
    assert done.status_code == 303, done.text
    db.expire_all()
    photos = db.query(Photo).filter(Photo.log_id == report["log"].id).all()
    assert len(photos) == 1 and photos[0].file_path.endswith(".jpg") and "vieja" not in photos[0].file_path
    assert db.get(DailyLog, report["log"].id).notes == ""


def test_report_detail_sends_photo_ids(login_as, report):
    data = login_as("worker").get(f"/logs/{report['log'].id}/detail").json()
    assert data["photos"][0]["id"] == report["photo"].id and "HEIC" in data["photo_rules"]


# --- Project form ---------------------------------------------------------------------------

def test_project_form_explains_what_saves_right_away(login_as):
    html = login_as("admin").get("/projects/new").text
    assert "Acceso al portal (usuarios del cliente)" in html
    assert "aunque después no guardes el proyecto" in html


# --- Quote tool -----------------------------------------------------------------------------

def test_only_admin_deletes_quotes(db, login_as):
    quote = Quote(numero_cotizacion="TCR-2026-0100", fecha_emision=date.today(), cliente_nombre="X",
                  cliente_datos={"name": "X"}, moneda="CRC", total=10, items=[])
    db.add(quote)
    db.commit()
    assert login_as("ventas").delete(f"/api/quotes/{quote.id}").status_code == 403
    assert 'canDelete: false' in login_as("ventas").get("/cotizador").text
    admin = login_as("admin")
    assert 'canDelete: true' in admin.get("/cotizador").text
    assert admin.delete(f"/api/quotes/{quote.id}").status_code == 200
    assert db.query(Quote).count() == 0
    assert db.query(ActivityLog).filter(ActivityLog.entity_type == "QUOTE").count() == 1


def test_discount_says_it_is_an_amount(login_as):
    assert "monto en la moneda, no %" in login_as("ventas").get("/cotizador").text


# --- Employees ------------------------------------------------------------------------------

def person(**extra):
    data = {"username": "nuevo", "password": "clave-segura", "full_name": "Nueva Persona", "role": "worker",
            "email": "nueva@example.com", "payment_method": "Efectivo"}
    data.update(extra)
    return data


def test_bad_document_creates_nobody(db, login_as):
    response = login_as("admin").post("/users/new", data=person(),
                                      files=[("files", ("virus.exe", b"MZ", "application/octet-stream"))],
                                      follow_redirects=False)
    assert response.status_code == 303 and response.headers["location"] == "/users/new"
    assert db.query(User).filter(User.username == "nuevo").count() == 0


def test_word_documents_are_accepted(db, login_as, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    docx = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    response = login_as("admin").post("/users/new", data=person(), files=[("files", ("contrato.docx", b"PK", docx))],
                                      follow_redirects=False)
    assert response.headers["location"] == "/users"
    doc = db.query(UserDocument).one()
    assert doc.filename == "contrato.docx" and doc.file_path.endswith(".docx")


def test_salary_only_suggests_the_rate(login_as):
    assert 'id="rate_hint"' in login_as("admin").get("/users/new").text


# --- Activity -------------------------------------------------------------------------------

def test_activity_search_covers_the_whole_history(db, login_as, users):
    for i in range(60):
        db.add(ActivityLog(user_id=users["admin"].id, action="UPDATE", entity_type="PROJECT", details=f"cambio {i}"))
    db.add(ActivityLog(user_id=users["worker"].id, action="DELETE", entity_type="REPORT", details="aguja en el pajar"))
    db.commit()
    client = login_as("admin")
    assert "aguja en el pajar" in client.get("/dashboard/activity?q=aguja").text
    assert "1 resultado(s)" in client.get("/dashboard/activity?q=pajar").text
    assert "hora de Costa Rica" in client.get("/dashboard/activity").text


def test_calendar_changes_are_recorded(db, login_as, users):
    client = login_as("supervisor")
    response = client.post("/calendar/schedule", data={"project_id": users["project_id"], "user_id": users["worker"].id,
                                                       "date": date.today().isoformat()})
    assert response.status_code == 200
    entry = db.query(ActivityLog).filter(ActivityLog.entity_type == "SCHEDULE").one()
    assert "Proyecto de prueba" in entry.details
