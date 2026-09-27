import os

# Must be set before any app module is imported: config.py reads SECRET_KEY at
# import time and load_dotenv() does not override variables already present.
os.environ["SECRET_KEY"] = "test-secret-key"
os.environ["USE_SQLITE"] = "True"
os.environ.setdefault("AWS_ACCESS_KEY_ID", "")
os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "")

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.main import app
from app.db.base import Base
from app.db.models.user import User
from app.db.models.project import Project
from app.core.security import pwd_context
from app.routers import deps

PASSWORD = "clave-de-prueba"
# Low bcrypt cost so the suite runs fast; verify_password reads the cost from the hash.
PASSWORD_HASH = pwd_context.hash(PASSWORD, rounds=4)
ROLES = ["admin", "supervisor", "worker", "client", "ventas"]

# TEST_DATABASE_URL runs the whole suite against another database (e.g. a
# disposable local PostgreSQL). Default: SQLite in memory.
TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL")
if TEST_DATABASE_URL:
    engine = create_engine(TEST_DATABASE_URL)
else:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


app.dependency_overrides[deps.get_db] = override_get_db


@pytest.fixture(autouse=True)
def fresh_db():
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def db():
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()


def make_user(db, username, role, **fields):
    user = User(
        username=username,
        hashed_password=PASSWORD_HASH,
        full_name=fields.pop("full_name", username),
        role=role,
        is_active=fields.pop("is_active", True),
        status=fields.pop("status", "active"),
        **fields,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture
def users(db):
    """One active user per role, all assigned to the same project."""
    created = {role: make_user(db, f"u_{role}", role) for role in ROLES}
    project = Project(name="Proyecto de prueba", is_active=True)
    project.users = [created["supervisor"], created["worker"], created["client"]]
    db.add(project)
    db.commit()
    created["project_id"] = project.id
    return created


def new_client(ip="200.1.113.10"):
    # A public IP by default, so per-IP throttling applies in tests.
    return TestClient(app, client=(ip, 50000))


def login(client, username, password=PASSWORD):
    return client.post(
        "/login",
        data={"user": username, "pass": password},
        follow_redirects=False,
    )


@pytest.fixture
def login_as(users):
    def _login_as(role):
        client = new_client()
        response = login(client, f"u_{role}")
        assert response.headers["location"] == "/dashboard", f"login failed for {role}"
        return client
    return _login_as
