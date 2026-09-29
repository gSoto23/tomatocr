"""UX round 1 (docs/PUNTOS_DIFICILES_UX.md, priority A): passwords, session messages,
the worker's assignments on the phone, photos, back-dated reports, the report e-mail and
the quote tool's numbering."""
import re
from datetime import date, timedelta
from io import BytesIO

import pytest
from PIL import Image

from app.core.security import verify_password
from app.db.models.log import DailyLog, Photo
from app.db.models.project_details import ProjectTask
from app.db.models.quote import Quote
from app.db.models.schedule import ProjectSchedule, ScheduleTask
from app.db.models.user import User
from app.routers import account as account_router
from app.routers import logs as logs_router
from app.utils import password_reset
from app.utils.timecr import today_cr
from tests.conftest import PASSWORD, login, new_client

# --- Passwords --------------------------------------------------------------------------


@pytest.fixture
def mails(monkeypatch):
    sent = []

    async def fake(recipients, subject, body):
        sent.append({"to": recipients, "subject": subject, "body": body})
    monkeypatch.setattr(account_router, "send_plain_email", fake)
    return sent


def test_change_own_password(db, login_as, users):
    client = login_as("worker")
    assert client.get("/cuenta/contrasena").status_code == 200
    bad = client.post("/cuenta/contrasena", data={"current": "otra", "new": "nueva-clave-1", "confirm": "nueva-clave-1"},
                      follow_redirects=False)
    assert bad.headers["location"] == "/cuenta/contrasena"
    short = client.post("/cuenta/contrasena", data={"current": PASSWORD, "new": "corta", "confirm": "corta"},
                        follow_redirects=False)
    assert short.headers["location"] == "/cuenta/contrasena"
    ok = client.post("/cuenta/contrasena", data={"current": PASSWORD, "new": "nueva-clave-1", "confirm": "nueva-clave-1"},
                     follow_redirects=False)
    assert ok.headers["location"] == "/dashboard"
    db.expire_all()
    assert verify_password("nueva-clave-1", db.get(User, users["worker"].id).hashed_password)


def test_recover_by_email_link(db, users, mails):
    worker = db.get(User, users["worker"].id)
    worker.email = "trabajador@example.com"
    db.commit()
    client = new_client()
    response = client.post("/recuperar", data={"identifier": "TRABAJADOR@example.com"}, follow_redirects=False)
    assert response.headers["location"] == "/recuperar?enviado=1"
    assert mails and mails[0]["to"] == ["trabajador@example.com"] and "u_worker" in mails[0]["body"]
    token = re.search(r"/recuperar/(\S+)", mails[0]["body"]).group(1)
    assert "Elegí tu contraseña nueva" in client.get(f"/recuperar/{token}").text
    mismatch = client.post(f"/recuperar/{token}", data={"new": "clave-nueva-1", "confirm": "otra-cosa-1"})
    assert mismatch.status_code == 400 and "no coinciden" in mismatch.text
    done = client.post(f"/recuperar/{token}", data={"new": "clave-nueva-1", "confirm": "clave-nueva-1"},
                       follow_redirects=False)
    assert done.headers["location"] == "/?ok=password_reset"
    assert login(new_client(), "u_worker", "clave-nueva-1").headers["location"] == "/dashboard"
    # The same link can't be used twice.
    assert "ya no sirve" in client.get(f"/recuperar/{token}").text


def test_recover_never_reveals_who_exists(db, users, mails):
    for identifier in ("nadie", "nadie@example.com", "u_client"):  # u_client has no e-mail
        response = new_client().post("/recuperar", data={"identifier": identifier}, follow_redirects=False)
        assert response.headers["location"] == "/recuperar?enviado=1"
    assert mails == []


def test_recover_is_rate_limited(db, users, mails):
    worker = db.get(User, users["worker"].id)
    worker.email = "trabajador@example.com"
    db.commit()
    for _ in range(5):
        new_client().post("/recuperar", data={"identifier": "u_worker"}, follow_redirects=False)
    assert len(mails) == password_reset.MAX_REQUESTS_PER_HOUR


def test_invalid_or_foreign_token(db, users):
    assert "ya no sirve" in new_client().get("/recuperar/no-es-un-token").text
    session_token = password_reset.jwt.encode({"sub": "u_worker"}, password_reset.settings.SECRET_KEY,
                                              algorithm=password_reset.settings.ALGORITHM)
    assert "ya no sirve" in new_client().get(f"/recuperar/{session_token}").text


def test_home_explains_session_messages():
    html = new_client().get("/").text
    assert "Tu sesión venció" in html and "¿Olvidaste tu contraseña?" in html and "password_reset" in html


# --- Worker assignments -------------------------------------------------------------------

def test_worker_sees_today_first_as_cards(db, login_as, users):
    today = today_cr()
    for days in (5, 0, -3):
        s = ProjectSchedule(project_id=users["project_id"], user_id=users["worker"].id, date=today + timedelta(days=days))
        db.add(s)
        db.flush()
        db.add(ScheduleTask(schedule_id=s.id, title='Tarea "con comillas"', description="<b>ok</b>"))
    db.commit()
    html = login_as("worker").get("/dashboard").text
    # Today's work is in the "Hoy" block at the top; the list below shows the next days, then the past ones.
    assert html.index("Mi trabajo de hoy") < html.index("Mis próximas asignaciones") < html.index("Anteriores")
    assert "Gestionar tareas" in html  # the phone card button
    assert "<b>ok</b>" not in html  # task text escaped


# --- Report: date and photos ----------------------------------------------------------------

def image_bytes(fmt="PNG", size=(3000, 2000)):
    buffer = BytesIO()
    Image.new("RGB", size, (40, 120, 60)).save(buffer, fmt)
    return buffer.getvalue()


def heic_bytes():
    import pillow_heif
    buffer = BytesIO()
    pillow_heif.from_pillow(Image.new("RGB", (800, 600), (200, 30, 30))).save(buffer, format="HEIF")
    return buffer.getvalue()


def report(client, users, day, files=()):
    return client.post("/logs/new", data={"project_id": users["project_id"], "date": day.isoformat(), "notes": "ok"},
                       files=[("photos", f) for f in files], follow_redirects=False)


@pytest.mark.parametrize("days_back,ok", [(0, True), (7, True), (8, False), (-1, False)])
def test_report_date_window(db, login_as, users, days_back, ok):
    response = report(login_as("worker"), users, today_cr() - timedelta(days=days_back))
    assert (response.status_code == 303) == ok
    if not ok:
        assert "últimos 7 días" in response.json()["detail"]


def test_photos_are_resized_and_heic_accepted(db, login_as, users, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "app" / "static" / "uploads").mkdir(parents=True)
    response = report(login_as("worker"), users, today_cr(), files=[
        ("grande.png", image_bytes(), "image/png"), ("iphone.heic", heic_bytes(), "image/heic")])
    assert response.status_code == 303, response.text
    photos = db.query(Photo).all()
    assert len(photos) == 2 and all(p.file_path.endswith(".jpg") for p in photos)
    for p in photos:
        with Image.open(tmp_path / "app" / p.file_path.lstrip("/")) as img:
            assert img.format == "JPEG" and max(img.size) <= 2048


def test_a_bad_photo_saves_nothing_and_names_the_file(db, login_as, users):
    response = report(login_as("worker"), users, today_cr(), files=[("nota.txt", b"hola", "text/plain")])
    assert response.status_code == 400 and "nota.txt" in response.json()["detail"]
    assert db.query(DailyLog).count() == 0


def test_report_form_offers_the_date_and_the_rules(login_as, users):
    html = login_as("worker").get(f"/logs/new?project_id={users['project_id']}").text
    assert 'type="date" id="report_date"' in html and "HEIC" in html and "20 MB" in html


# --- Report e-mail -------------------------------------------------------------------------

@pytest.fixture
def a_report(db, users):
    log = DailyLog(project_id=users["project_id"], user_id=users["worker"].id, date=today_cr(), notes="ok")
    db.add(log)
    db.commit()
    return log


def test_email_uses_a_real_blind_copy_and_reports_failure(db, login_as, a_report, monkeypatch):
    calls = []

    async def fake(log_id, recipients, additional, notes, bcc=None):
        calls.append({"to": recipients, "bcc": bcc})
        return len(calls) == 1
    monkeypatch.setattr(logs_router, "send_log_email", fake)
    client = login_as("admin")
    body = {"recipients": ["cliente@example.com", "info@tomatocr.com"]}
    assert client.post(f"/logs/{a_report.id}/send-email", json=body).status_code == 200
    assert calls[0] == {"to": ["cliente@example.com"], "bcc": ["info@tomatocr.com"]}
    failed = client.post(f"/logs/{a_report.id}/send-email", json=body)
    assert failed.status_code == 502 and "No se pudo enviar" in failed.json()["detail"]


# --- Quote numbering ------------------------------------------------------------------------

def quote(number, **extra):
    data = {"numero_cotizacion": number, "fecha_emision": date.today().isoformat(), "cliente_nombre": "X",
            "cliente_datos": {"name": "X"}, "moneda": "CRC", "total": 1000, "items": [], "account_id": None}
    data.update(extra)
    return data


@pytest.fixture
def account(db):
    from app.db.models.crm import Account
    a = Account(name="Hotel Bosque")
    db.add(a)
    db.commit()
    return a


def test_two_new_quotes_with_the_same_number_never_overwrite(db, login_as, account):
    number = f"TCR-{date.today().year}-0007"
    first = login_as("ventas").post("/api/quotes/", json=quote(number, account_id=account.id, total=100)).json()
    second = login_as("admin").post("/api/quotes/", json=quote(number, account_id=account.id, total=200)).json()
    assert first["numero_cotizacion"] == number and second["renumbered_from"] == number
    assert second["numero_cotizacion"] != number and first["id"] != second["id"]
    assert db.query(Quote).count() == 2 and db.get(Quote, first["id"]).total == 100


def test_saving_a_loaded_quote_updates_it_by_id(db, login_as, account):
    client = login_as("ventas")
    first = client.post("/api/quotes/", json=quote(f"TCR-{date.today().year}-0001", account_id=account.id)).json()
    again = client.post("/api/quotes/", json=quote(first["numero_cotizacion"], id=first["id"], account_id=account.id,
                                                   total=5000)).json()
    assert again["id"] == first["id"] and db.query(Quote).count() == 1
    db.expire_all()
    assert db.get(Quote, first["id"]).total == 5000


def test_cotizador_offers_to_recover_a_draft(login_as):
    html = login_as("ventas").get("/cotizador").text
    assert 'id="draftBanner"' in html and "Descartar cambios" in html


def test_password_page_help_opens_first_steps():
    from app.utils.manual import help_url
    assert help_url("/cuenta/contrasena", "worker") == "/manual/primeros-pasos"
