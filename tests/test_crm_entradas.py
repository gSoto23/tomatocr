"""Fase 2D: leads from the contact form and darboles.com, assignment, erasure,
account rename and the sales-board import."""
import pytest

from app.core.config import settings
from app.db.models.activity import ActivityLog
from app.db.models.crm import Account, Contact, CrmActivity, CrmAssignment, LeadSubmission, Opportunity, ProjectContactRole
from app.db.models.project import Project
from app.db.models.project_details import ProjectContact
from app.routers import leads as leads_router
from app.utils.crm import ANONYMIZED_NAME
from app.utils.tablero import import_leads, split_contact_data
from tests.conftest import make_user, new_client

FORM = {"name": "Laura Mora", "company": "Hotel Bosque", "email": "Laura@HotelBosque.cr", "phone": "",
        "motor": "mantenimiento", "message": "Jardines de 2 hectáreas", "consent": True}
KEY = "clave-darboles-de-prueba"


@pytest.fixture(autouse=True)
def mails(monkeypatch):
    sent = []

    async def fake_send(recipients, subject, body):
        sent.append({"to": recipients, "subject": subject, "body": body})
    monkeypatch.setattr(leads_router, "send_plain_email", fake_send)
    return sent


@pytest.fixture
def sellers(db, users):
    melina = make_user(db, "melina", "ventas", full_name="Melina Rojas")
    albert = make_user(db, "albert", "ventas", full_name="Albert Solís")
    gerardo = make_user(db, "gerardo", "admin", full_name="Gerardo Soto")
    db.add_all([CrmAssignment(motor="esg", user_id=melina.id), CrmAssignment(motor="mantenimiento", user_id=albert.id),
                CrmAssignment(motor="_default", user_id=gerardo.id)])
    db.commit()
    return {"melina": melina, "albert": albert, "gerardo": gerardo}


def post_form(data, ip="200.1.113.10", json_body=True):
    client = new_client(ip)
    if json_body:
        return client.post("/contacto", json=data, headers={"Accept": "application/json"})
    return client.post("/contacto", data=data, follow_redirects=False)


# --- Contact form ------------------------------------------------------------------------

def test_form_creates_account_contact_and_opportunity_for_the_motor_seller(db, sellers, mails):
    response = post_form(FORM)
    assert response.status_code == 200 and response.json()["ok"]
    account = db.query(Account).one()
    assert account.name == "Hotel Bosque" and account.owner_id == sellers["albert"].id and account.source == "web"
    contact = db.query(Contact).one()
    assert contact.email == "laura@hotelbosque.cr" and contact.consent_marketing and contact.consent_at
    assert contact.consent_text_version
    opp = db.query(Opportunity).one()
    assert (opp.motor, opp.stage, opp.owner_id) == ("mantenimiento", "prospecto", sellers["albert"].id)
    assert opp.next_step == "Responder la solicitud"
    note = db.query(CrmActivity).one()
    assert "Jardines de 2 hectáreas" in note.notes
    assert len(mails) == 1 and settings.LEADS_NOTIFY_EMAIL in mails[0]["to"]
    assert mails[0]["subject"] == "Nueva oportunidad: Hotel Bosque (Mantenimiento)"
    assert f"/clientes/oportunidades/{opp.id}" in mails[0]["body"]


def test_form_without_javascript_redirects_to_thanks(db, sellers):
    data = {**FORM, "consent": "true"}
    response = post_form(data, json_body=False)
    assert response.status_code == 303 and response.headers["location"] == "/contacto/gracias"
    assert db.query(Opportunity).count() == 1


def test_second_request_does_not_duplicate(db, sellers):
    post_form(FORM)
    post_form({**FORM, "email": "laura@hotelbosque.cr", "message": "Otra consulta"}, ip="200.1.113.11")
    post_form({**FORM, "email": "otro@hotelbosque.cr", "company": "HOTEL BOSQUE", "motor": "esg"}, ip="200.1.113.12")
    assert db.query(Account).count() == 1
    assert db.query(Contact).count() == 2
    # Same motor while open → a note on the same opportunity; other motor → a new one.
    assert db.query(Opportunity).count() == 2
    assert db.query(CrmActivity).count() == 3


def test_existing_account_keeps_its_owner(db, sellers, users):
    db.add(Account(name="Hotel Bosque", owner_id=users["ventas"].id))
    db.commit()
    post_form(FORM)
    assert db.query(Opportunity).one().owner_id == users["ventas"].id


def test_motor_without_seller_goes_to_default(db, sellers):
    post_form({**FORM, "motor": "tienda"})
    assert db.query(Opportunity).one().owner_id == sellers["gerardo"].id


@pytest.mark.parametrize("change,message", [
    ({"consent": False}, "política de privacidad"),
    ({"email": "", "phone": ""}, "correo o un teléfono"),
    ({"email": "no-es-correo"}, "no parece válido"),
    ({"motor": "otra_cosa"}, "Elegí qué te interesa"),
    ({"name": " "}, "nombre"),
])
def test_form_validation(db, sellers, change, message):
    response = post_form({**FORM, **change})
    assert response.status_code == 400 and message in response.json()["message"]
    assert db.query(Account).count() == 0


def test_honeypot_pretends_success_and_saves_nothing(db, sellers, mails):
    response = post_form({**FORM, "website": "http://spam"})
    assert response.json()["ok"]
    assert db.query(Account).count() == 0 and db.query(LeadSubmission).count() == 0 and not mails


def test_rate_limit_per_ip(db, sellers, monkeypatch):
    monkeypatch.setattr(settings, "LEADS_PER_IP_PER_HOUR", 2)
    for i in range(2):
        assert post_form({**FORM, "email": f"p{i}@x.cr"}).status_code == 200
    assert post_form({**FORM, "email": "p9@x.cr"}).status_code == 429
    assert post_form({**FORM, "email": "p8@x.cr"}, ip="200.1.113.99").status_code == 200


def test_global_hourly_limit(db, sellers, monkeypatch):
    monkeypatch.setattr(settings, "LEADS_PER_HOUR", 1)
    assert post_form(FORM).status_code == 200
    assert post_form({**FORM, "email": "b@x.cr"}, ip="200.1.113.50").status_code == 429


def test_public_pages_have_the_form_and_privacy_data():
    client = new_client()
    for path in ("/", "/programas/darboles"):
        html = client.get(path).text
        assert 'data-contact-form' in html and 'name="website"' in html and "/privacidad" in html
    privacy = client.get("/privacidad").text
    assert "3-102-876296" in privacy and "info@tomatocr.com" in privacy and "8968" in privacy
    assert "/privacidad" in client.get("/sitemap.xml").text


# --- darboles.com API --------------------------------------------------------------------

def api(data, key=KEY):
    return new_client().post("/api/crm/leads", json=data, headers={"X-API-Key": key} if key else {})


def test_api_disabled_without_key(db, sellers, monkeypatch):
    monkeypatch.setattr(settings, "DARBOLES_API_KEY", "")
    assert api(FORM).status_code == 503


def test_api_rejects_wrong_or_missing_key(db, sellers, monkeypatch):
    monkeypatch.setattr(settings, "DARBOLES_API_KEY", KEY)
    assert api(FORM, key="otra").status_code == 401
    assert api(FORM, key=None).status_code == 401
    assert db.query(Account).count() == 0


def test_api_creates_lead(db, sellers, monkeypatch):
    monkeypatch.setattr(settings, "DARBOLES_API_KEY", KEY)
    response = api({**FORM, "motor": "esg"})
    assert response.status_code == 200
    body = response.json()
    assert body["new_account"] and body["new_opportunity"]
    opp = db.get(Opportunity, body["opportunity_id"])
    assert opp.source == "darboles" and opp.owner_id == sellers["melina"].id
    assert api({**FORM, "consent": False}).status_code == 422


def test_api_has_no_cors(monkeypatch):
    monkeypatch.setattr(settings, "DARBOLES_API_KEY", KEY)
    response = new_client().options("/api/crm/leads", headers={"Origin": "https://evil.example",
                                                               "Access-Control-Request-Method": "POST"})
    assert "access-control-allow-origin" not in response.headers


# --- Assignment page -----------------------------------------------------------------------

def test_assignment_page_admin_only(login_as, sellers):
    assert login_as("ventas").get("/clientes/asignacion", follow_redirects=False).status_code in (302, 303, 403)
    page = login_as("admin").get("/clientes/asignacion")
    assert page.status_code == 200 and "Melina Rojas" in page.text


def test_assignment_saves(login_as, db, sellers):
    client = login_as("admin")
    response = client.post("/clientes/asignacion", data={"esg": str(sellers["albert"].id), "tienda": "999999",
                                                        "_default": str(sellers["gerardo"].id)},
                           follow_redirects=False)
    assert response.status_code == 303
    db.expire_all()
    assert db.get(CrmAssignment, "esg").user_id == sellers["albert"].id
    assert db.get(CrmAssignment, "tienda").user_id is None  # not a seller
    assert db.get(CrmAssignment, "mantenimiento").user_id is None
    assert db.query(ActivityLog).filter(ActivityLog.entity_type == "CRM_ASSIGNMENT").count() == 1


# --- Erasure ----------------------------------------------------------------------------

def test_anonymize_contact(login_as, db, sellers, users):
    post_form(FORM)
    contact = db.query(Contact).one()
    project = Project(name="Jardines Bosque", account_id=contact.account_id)
    db.add(project)
    db.flush()
    db.add(ProjectContact(project_id=project.id, name="Laura", email="laura@hotelbosque.cr"))
    db.add(ProjectContactRole(project_id=project.id, contact_id=contact.id, receives_reports=True))
    db.commit()
    assert login_as("ventas").post(f"/clientes/contactos/{contact.id}/anonimizar",
                                   follow_redirects=False).status_code in (302, 303, 403)
    response = login_as("admin").post(f"/clientes/contactos/{contact.id}/anonimizar", follow_redirects=False)
    assert response.status_code == 303
    db.expire_all()
    contact = db.get(Contact, contact.id)
    assert (contact.name, contact.email, contact.phone, contact.consent_at) == (ANONYMIZED_NAME, None, None, None)
    assert db.query(ProjectContact).one().email is None
    assert db.query(ProjectContactRole).count() == 0
    note = db.query(CrmActivity).one()
    assert "Jardines de 2" not in note.notes and note.notes.startswith("Solicitud desde")
    assert db.query(Opportunity).count() == 1


def test_contact_with_portal_access_is_not_anonymized(login_as, db, users):
    account = Account(name="Museo")
    db.add(account)
    db.flush()
    contact = Contact(account_id=account.id, name="Portal", user_id=users["client"].id)
    db.add(contact)
    db.commit()
    login_as("admin").post(f"/clientes/contactos/{contact.id}/anonimizar", follow_redirects=False)
    db.expire_all()
    assert db.get(Contact, contact.id).name == "Portal"


# --- Account rename ---------------------------------------------------------------------

def test_rename_account_updates_projects_that_used_the_old_name(login_as, db, users):
    account = Account(name="Condominio Sol")
    db.add(account)
    db.flush()
    same = Project(name="P1", account_id=account.id, client_display_name="CONDOMINIO SOL")
    own = Project(name="P2", account_id=account.id, client_display_name="Sol · Torre B")
    db.add_all([same, own])
    db.commit()
    login_as("admin").post(f"/clientes/cuentas/{account.id}/editar", data={"name": "Condominio Sol Naciente"},
                           follow_redirects=False)
    db.expire_all()
    assert db.get(Project, same.id).client_display_name == "Condominio Sol Naciente"
    assert db.get(Project, own.id).client_display_name == "Sol · Torre B"


# --- Sales-board import -----------------------------------------------------------------

BOARD = [
    {"id": "a1", "empresa": "Banco Verde", "contacto": "Sofía", "cargo": "RSE", "dato": "sofia@bancoverde.cr",
     "motor": "ESG", "fuente": "LinkedIn", "etapa": "reunion", "alcanzo": 2, "responsable": "Melina",
     "proximo": "Enviar propuesta", "fecha": "2026-10-20", "notas": "Interesados en 500 árboles",
     "creado": "2026-10-15", "actualizado": "2026-10-18"},
    {"id": "a2", "empresa": "Municipalidad de Grecia", "contacto": "", "cargo": "", "dato": "2444-0000",
     "motor": "Sector público", "fuente": "SICOP", "etapa": "perdido", "alcanzo": 3, "responsable": "Alina",
     "proximo": "", "fecha": "", "notas": "", "creado": "2026-10-16", "actualizado": "2026-10-17"},
    {"id": "a3", "empresa": "Hotel Bosque", "contacto": "Laura", "dato": "laura@hotelbosque.cr",
     "motor": "Mantenimiento", "fuente": "Web", "etapa": "cerrado", "alcanzo": 4, "responsable": "Albert",
     "creado": "2026-10-16", "actualizado": "2026-10-19"},
    {"id": "a4", "empresa": "", "motor": "ESG", "etapa": "prospecto"},
    {"id": "a5", "empresa": "X", "motor": "Otro", "etapa": "prospecto"},
]


def test_split_contact_data():
    assert split_contact_data("Correo: Ana@X.cr")["email"] == "ana@x.cr"
    assert split_contact_data("+506 8888-7777")["phone"] == "+506 8888-7777"
    assert split_contact_data("por LinkedIn")["other"] == "por LinkedIn"


def test_import_board(db, sellers):
    db.add(Account(name="Hotel Bosque"))
    db.commit()
    report = import_leads(db, BOARD, sellers["gerardo"])
    db.commit()
    assert report.counts == {"importado": 3, "error": 2, "cuentas nuevas": 2}
    banco = db.query(Opportunity).filter_by(origin_ref="tablero:a1").one()
    assert (banco.motor, banco.stage, banco.max_stage, banco.owner_id) == ("esg", "reunion", 2, sellers["melina"].id)
    assert banco.next_step == "Enviar propuesta" and str(banco.next_step_date) == "2026-10-20"
    assert banco.source == "linkedin" and banco.account.contacts[0].email == "sofia@bancoverde.cr"
    muni = db.query(Opportunity).filter_by(origin_ref="tablero:a2").one()
    assert (muni.stage, muni.max_stage, muni.owner_id) == ("perdido", 3, sellers["gerardo"].id)
    assert muni.account.kind == "institucion_publica" and muni.account.contacts[0].phone == "2444-0000"
    assert "Alina" in db.query(CrmActivity).filter_by(opportunity_id=muni.id).one().notes  # no user named Alina
    hotel = db.query(Opportunity).filter_by(origin_ref="tablero:a3").one()
    assert hotel.stage == "ganado" and db.query(Account).filter_by(name="Hotel Bosque").count() == 1

    again = import_leads(db, BOARD, sellers["gerardo"])
    assert again.counts == {"omitido": 3, "error": 2}
    assert db.query(Opportunity).count() == 3


def test_import_empty_board(db, sellers):
    assert import_leads(db, [], sellers["gerardo"]).counts == {}


def test_public_texts_use_vos():
    """Tone of the public site (docs/DISENO_CRM.md, section 6): vos, never usted."""
    client = new_client()
    for path in ("/", "/programas/darboles", "/proyectos-reforestacion", "/privacidad", "/contacto/gracias"):
        html = client.get(path).text
        for formal in ("usted", "Escríbanos", "Déjenos", "Elija ", "Le contactaremos", "¿Qué le interesa", "Prefiere",
                       "Contáctenos", "Solicite", "Escriba ", "Indique", "Revise ", "Intente "):
            assert formal not in html, (path, formal)


# --- What visitors see in the form -------------------------------------------------------

def test_form_options_speak_the_clients_language_and_keep_the_motors():
    from app.db.models.crm import MOTORS
    from app.routers.leads import PUBLIC_MOTOR_LABELS
    # every CRM motor except the store, whose purchases happen on darboles.com
    assert set(PUBLIC_MOTOR_LABELS) == set(MOTORS) - {"tienda"}
    client = new_client()
    home = client.get("/").text
    assert "Mantenimiento, jardinería o paisajismo" in home and "Reforestación para mi empresa (ESG)" in home
    form = home[home.index("data-contact-form"):home.index("</form>", home.index("data-contact-form"))]
    assert '<option value="">Elegí una opción</option>' in form and "selected" not in form
    assert 'data-motor="mantenimiento"' in home  # "Cotizar este servicio" preselects it
    darboles = client.get("/programas/darboles").text
    assert '<option value="esg" selected>' in darboles


def test_success_promises_the_24_hour_answer(db, sellers):
    answer = post_form(FORM).json()
    assert answer["ok"] and "24 horas" in answer["message"]
    assert "24 horas" in new_client().get("/contacto/gracias").text


def test_form_does_not_offer_the_store_but_the_api_still_accepts_it(db, sellers, monkeypatch):
    monkeypatch.setattr(settings, "DARBOLES_API_KEY", KEY)
    for path in ("/", "/programas/darboles", "/servicios/mantenimiento-de-zonas-verdes"):
        html = new_client().get(path).text
        assert 'value="tienda"' not in html and "Compra en la tienda" not in html
    assert api({**FORM, "email": "tienda@x.cr", "motor": "tienda"}).status_code == 200
