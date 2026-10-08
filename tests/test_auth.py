from datetime import timedelta

import pytest

from app.db.models.activity import ActivityLog
from app.db.models.login_attempt import LoginAttempt
from app.db.models.user import User
from app.utils.login_throttle import trackable_ip
from tests.conftest import PASSWORD, login, make_user, new_client


def test_active_user_logs_in(db):
    make_user(db, "activo", "worker")
    client = new_client()
    response = login(client, "activo")
    assert response.status_code == 303
    assert response.headers["location"] == "/dashboard"
    assert "access_token" in response.cookies


def test_wrong_password_is_rejected(db):
    make_user(db, "activo", "worker")
    response = login(new_client(), "activo", "incorrecta")
    assert response.headers["location"] == "/?error=invalid_credentials"
    assert "access_token" not in response.cookies


@pytest.mark.parametrize("fields", [
    {"is_active": False},
    {"status": "inactive"},
    {"status": "liquidated"},
    {"is_active": False, "status": "liquidated"},
])
def test_inactive_user_cannot_log_in(db, fields):
    make_user(db, "inactivo", "worker", **fields)
    response = login(new_client(), "inactivo")
    # Only with the right password does it say the user is deactivated.
    assert response.headers["location"] == "/?error=inactive"
    assert "access_token" not in response.cookies
    wrong = login(new_client(), "inactivo", "incorrecta")
    assert wrong.headers["location"] == "/?error=invalid_credentials"


def test_null_status_is_treated_as_active(db):
    user = make_user(db, "legado", "worker")
    user.status = None
    user.is_active = None
    db.commit()
    assert login(new_client(), "legado").headers["location"] == "/dashboard"


def test_existing_token_stops_working_after_deactivation(db):
    user = make_user(db, "sesion", "supervisor")
    client = new_client()
    login(client, "sesion")
    assert client.get("/dashboard/", follow_redirects=False).status_code == 200

    user.is_active = False
    db.commit()

    response = client.get("/dashboard/", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/?error=login_required"
    assert 'access_token=""' in response.headers["set-cookie"] or "access_token=;" in response.headers["set-cookie"]


def fail(client, username, times):
    for _ in range(times):
        login(client, username, "incorrecta")


def test_five_failures_lock_the_username(db):
    make_user(db, "victima", "admin")
    client = new_client()
    fail(client, "victima", 5)

    # Even the right password is refused while locked, from any IP.
    response = login(new_client("200.2.100.7"), "victima")
    assert response.headers["location"] == "/?error=too_many_attempts"

    blocks = db.query(ActivityLog).filter(ActivityLog.action == "LOGIN_BLOCKED").all()
    assert len(blocks) == 1
    assert "victima" in blocks[0].details


def test_four_failures_do_not_lock(db):
    make_user(db, "casi", "admin")
    client = new_client()
    fail(client, "casi", 4)
    assert login(client, "casi").headers["location"] == "/dashboard"


def test_success_resets_the_username_counter(db):
    make_user(db, "reinicio", "admin")
    fail(new_client("200.2.100.1"), "reinicio", 4)
    assert login(new_client("200.2.100.2"), "reinicio").headers["location"] == "/dashboard"
    fail(new_client("200.2.100.3"), "reinicio", 4)
    assert login(new_client("200.2.100.4"), "reinicio").headers["location"] == "/dashboard"


def test_lock_expires_after_15_minutes(db):
    make_user(db, "espera", "admin")
    fail(new_client(), "espera", 5)
    assert login(new_client(), "espera").headers["location"] == "/?error=too_many_attempts"

    for attempt in db.query(LoginAttempt).all():
        attempt.created_at = attempt.created_at - timedelta(minutes=16)
    db.commit()

    assert login(new_client(), "espera").headers["location"] == "/dashboard"


def test_blocked_attempts_do_not_extend_the_lock(db):
    make_user(db, "insiste", "admin")
    fail(new_client(), "insiste", 5)
    fail(new_client(), "insiste", 10)  # refused while locked, not recorded
    assert db.query(LoginAttempt).filter(LoginAttempt.username == "insiste").count() == 5


def test_a_shared_office_ip_is_not_locked_by_a_few_typos(db):
    # A whole office shares one public IP: 5 failures of other people don't lock it.
    make_user(db, "otro", "admin")
    office = "200.1.113.99"
    for i in range(5):
        login(new_client(office), f"inexistente{i}", "x")
    assert login(new_client(office), "otro").headers["location"] == "/dashboard"


def test_twenty_failures_from_one_public_ip_lock_that_ip(db):
    from app.utils.login_throttle import MAX_IP_FAILURES
    make_user(db, "otro", "admin")
    attacker = "200.1.113.98"
    for i in range(MAX_IP_FAILURES):
        login(new_client(attacker), f"inexistente{i}", "x")
    assert login(new_client(attacker), "otro").headers["location"] == "/?error=too_many_attempts"
    # Another IP is not affected.
    assert login(new_client("200.1.113.100"), "otro").headers["location"] == "/dashboard"


def test_login_is_with_the_username_not_the_email(db):
    make_user(db, "melina", "ventas", email="melina@tomatocr.com")
    assert login(new_client(), "melina@tomatocr.com").headers["location"] == "/?error=invalid_credentials"
    assert login(new_client(), " melina ").headers["location"] == "/dashboard"  # spaces at the ends don't count
    assert login(new_client(), "Melina").headers["location"] == "/?error=invalid_credentials"


def test_new_user_is_saved_without_spaces(db, admin_client):
    from app.db.models.user import User
    client, _ = admin_client
    client.post("/users/new", data=user_form(username="  nuevo  "), follow_redirects=False)
    assert db.query(User).filter(User.username == "nuevo").count() == 1


def test_private_ip_is_not_locked(db):
    # Behind a proxy everyone may share a private IP; locking it would lock everyone.
    make_user(db, "oficina", "admin")
    for i in range(5):
        login(new_client("127.0.0.1"), f"inexistente{i}", "x")
    assert login(new_client("127.0.0.1"), "oficina").headers["location"] == "/dashboard"


@pytest.mark.parametrize("ip,expected", [
    ("200.1.113.5", "200.1.113.5"),
    ("127.0.0.1", None),
    ("10.0.0.4", None),
    ("172.26.9.22", None),
    ("192.168.1.2", None),
    ("::1", None),
    ("testclient", None),
    (None, None),
])
def test_trackable_ip(ip, expected):
    assert trackable_ip(ip) == expected


# --- User administration -------------------------------------------------

@pytest.fixture
def admin_client(db):
    admin = make_user(db, "jefe", "admin")
    client = new_client()
    login(client, "jefe")
    return client, admin


def user_form(**overrides):
    data = {"username": "nuevo", "password": PASSWORD, "full_name": "Nuevo", "role": "ventas", "is_active": "true",
            "email": "nuevo@example.com"}
    data.update(overrides)
    return data


def test_admin_can_create_ventas_user(db, admin_client):
    client, _ = admin_client
    client.post("/users/new", data=user_form(), follow_redirects=False)
    assert db.query(User).filter(User.username == "nuevo").one().role == "ventas"


@pytest.mark.parametrize("email", ["", "no-es-correo"])
def test_email_is_required(db, admin_client, email):
    client, _ = admin_client
    response = client.post("/users/new", data=user_form(email=email), follow_redirects=False)
    assert response.headers["location"] == "/users/new"
    assert db.query(User).filter(User.username == "nuevo").first() is None


def test_users_without_email_are_listed(db, admin_client):
    client, _ = admin_client
    make_user(db, "sin_correo", "worker", full_name="Sin Correo")
    assert "Sin Correo" in client.get("/users").text and "sin correo" in client.get("/users").text


def test_unknown_role_is_rejected(db, admin_client):
    client, _ = admin_client
    response = client.post("/users/new", data=user_form(role="superadmin"), follow_redirects=False)
    assert response.headers["location"] == "/users/new"
    assert db.query(User).filter(User.username == "nuevo").first() is None


def test_unknown_role_is_rejected_on_edit(db, admin_client):
    client, _ = admin_client
    target = make_user(db, "editado", "worker")
    client.post(f"/users/{target.id}/edit", data=user_form(username="editado", role="root"), follow_redirects=False)
    db.refresh(target)
    assert target.role == "worker"


@pytest.mark.parametrize("change", ["deactivate", "demote"])
def test_admin_cannot_lock_themselves_out(db, admin_client, change):
    client, admin = admin_client
    data = user_form(username="jefe", role="admin")
    if change == "deactivate":
        data.pop("is_active")  # unchecked checkbox
    else:
        data["role"] = "worker"
    response = client.post(f"/users/{admin.id}/edit", data=data, follow_redirects=False)
    assert response.headers["location"] == f"/users/{admin.id}/edit"
    db.refresh(admin)
    assert admin.is_active is True
    assert admin.role == "admin"
