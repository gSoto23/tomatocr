"""The public contact form against bots: real phones and names, and requests that look like a
bot (gibberish, throwaway e-mail, posted at once) kept in Descartados without e-mail."""
import time

import pytest

from app.core.config import settings
from app.db.models.crm import Account, Contact, Opportunity
from app.utils.spam import form_token, phone_problem, spam_reasons
from tests.conftest import new_client
from tests.test_crm_entradas import FORM, mails, post_form, sellers  # noqa: F401 (fixtures)

BOT = {"name": "NAYUYUTY410456NEYRTHYT", "company": "google", "email": "volny98@belettersmail.com",
       "phone": "82769142553", "motor": "sector_publico", "message": "MERTYHRTHYHT410456MARTHHDF",
       "consent": True}


@pytest.mark.parametrize("phone", ["8888 8888", "2440-1234", "7080-8613", "+506 7080 8613", "50670808613",
                                   "(506) 6000-0000", "+1 305 555 0100", "+44 20 7946 0958"])
def test_good_phones(phone):
    assert phone_problem(phone) is None


@pytest.mark.parametrize("phone", ["8888", "1234 5678", "82769142553", "+506 1234 5678", "+44 20", "88 88 88 8x"])
def test_bad_phones(phone):
    assert phone_problem(phone)


def test_a_person_sees_what_to_fix(db, sellers, mails):  # noqa: F811
    response = post_form({**FORM, "phone": "8888"})
    assert response.status_code == 400 and "teléfono" in response.json()["message"]
    response = post_form({**FORM, "name": "Laura 2"})
    assert response.status_code == 400 and "sin números" in response.json()["message"]
    assert db.query(Account).count() == 0 and mails == []
    assert post_form({**FORM, "phone": "+506 8888-8888"}).json()["ok"]


def test_a_bot_gets_thanks_and_lands_in_descartados(db, sellers, mails, login_as):  # noqa: F811
    response = post_form(BOT)
    assert response.status_code == 200 and response.json()["ok"]  # nothing tells the bot it was caught
    assert mails == []  # no e-mail to sellers or info@
    account = db.query(Account).one()
    assert account.discarded_at and account.discard_reason.startswith("Spam automático: ")
    assert "texto sin sentido en nombre" in account.discard_reason and "correo desechable" in account.discard_reason
    opportunity = db.query(Opportunity).one()
    assert opportunity.stage == "perdido" and opportunity.lost_reason == account.discard_reason
    assert "google" in login_as("admin").get("/clientes/descartados").text
    assert "google" not in login_as("admin").get("/clientes").text


@pytest.mark.parametrize("token,reason", [
    ("", "sin la marca del formulario"),
    ("123.abc", "marca del formulario alterada"),
])
def test_missing_or_tampered_token(db, sellers, mails, token, reason):  # noqa: F811
    new_client().post("/contacto", json={**FORM, "form_token": token}, headers={"Accept": "application/json"})
    account = db.query(Account).one()
    assert reason in account.discard_reason and mails == []


def test_posted_at_once(db, sellers, mails):  # noqa: F811
    post_form({**FORM, "form_token": form_token(time.time())})
    assert "enviado en" in db.query(Account).one().discard_reason and mails == []


def test_spam_never_touches_an_existing_client(db, sellers, mails):  # noqa: F811
    client = Account(name="google")
    db.add(client)
    db.flush()
    db.add(Contact(account_id=client.id, name="Real", email="volny98@belettersmail.com"))
    db.commit()
    post_form(BOT)
    db.expire_all()
    assert db.get(Account, client.id).discarded_at is None
    assert db.query(Account).count() == 2


def test_people_writing_codes_are_not_spam():
    lead = {"name": "Ana Mora", "company": "Municipalidad", "email": "ana@muni.go.cr",
            "message": "Licitación 2025LD-000082-0000500001, 300m2 de zacate, cotización TCR-2026-0010."}
    assert spam_reasons(lead, form_token(time.time() - 30)) == []


def test_darboles_api_keeps_its_rules(db, sellers, monkeypatch, mails):  # noqa: F811
    monkeypatch.setattr(settings, "DARBOLES_API_KEY", "clave")
    response = new_client().post("/api/crm/leads", json={**FORM, "phone": "123"}, headers={"X-API-Key": "clave"})
    assert response.status_code == 200  # the strict phone and token checks are only for the web form


def test_form_carries_the_token():
    html = new_client().get("/").text
    assert 'name="form_token" value="' in html and 'id="contact-error-phone"' in html


def test_real_ip_behind_nginx(db, sellers, mails):  # noqa: F811
    from app.db.models.crm import LeadSubmission
    proxy = new_client("127.0.0.1")
    proxy.post("/contacto", json={**FORM, "form_token": form_token(time.time() - 60)},
               headers={"Accept": "application/json", "X-Forwarded-For": "1.1.1.1, 200.9.9.9"})
    assert db.query(LeadSubmission).one().ip_address == "200.9.9.9"  # the entry nginx adds
    outsider = new_client("190.1.1.1")
    outsider.post("/contacto", json={**FORM, "email": "otra@x.cr", "form_token": form_token(time.time() - 60)},
                  headers={"Accept": "application/json", "X-Forwarded-For": "8.8.8.8"})
    assert {s.ip_address for s in db.query(LeadSubmission)} == {"200.9.9.9", "190.1.1.1"}  # faked header ignored


@pytest.mark.parametrize("company", ["Soluciones360Group", "Servicios2024CR", "3M Costa Rica", "Grupo 506 S.A.",
                                     "3-101-123456 S.A.", "Constructora MV2020"])
def test_companies_with_numbers_are_not_spam_on_their_own(company):
    lead = {"name": "Ana Mora", "company": company, "email": "ana@empresa.cr", "message": "Necesito mantenimiento."}
    assert spam_reasons(lead, form_token(time.time() - 30)) == []


def test_company_adds_to_other_signs():
    lead = {"name": "Ana Mora", "company": "Servicios2024CR", "email": "x@belettersmail.com", "message": ""}
    assert spam_reasons(lead, form_token(time.time() - 30)) == ["correo desechable (belettersmail.com)",
                                                                  "texto sin sentido en empresa"]


def test_real_company_with_numbers_reaches_the_seller(db, sellers, mails):  # noqa: F811
    assert post_form({**FORM, "company": "Soluciones360Group"}).json()["ok"]
    assert db.query(Account).one().discarded_at is None and len(mails) == 1
