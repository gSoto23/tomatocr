"""Copy script test. Needs a disposable PostgreSQL, e.g.:

    docker run -d --name tomato-pg17 -e POSTGRES_USER=tomato -e POSTGRES_PASSWORD=tomato-local \
        -e POSTGRES_DB=tomato -p 55432:5432 postgres:17
    TEST_POSTGRES_URL=postgresql://tomato:tomato-local@127.0.0.1:55432/tomato pytest tests/test_sqlite_to_postgres.py

The target database is wiped. Skipped when TEST_POSTGRES_URL is not set.
"""
import datetime
import os

import pytest
from sqlalchemy import (JSON, Boolean, Date, DateTime, Enum, Float, Integer, String, Text,
                        create_engine, func, select, text)

from app.db.base import Base
from app.db.models.user import User
from scripts.sqlite_to_postgres import CopyError, copy

PG_URL = os.environ.get("TEST_POSTGRES_URL")
pytestmark = pytest.mark.skipif(not PG_URL, reason="TEST_POSTGRES_URL not set")

ROWS_PER_TABLE = 2


def sample_value(column, i):
    """Row 1 fills every column; row 2 leaves nullable columns empty."""
    if column.primary_key and isinstance(column.type, Integer) and not column.foreign_keys:
        return i
    if column.foreign_keys:
        return i
    if i == 2 and column.nullable:
        return None
    t = column.type
    if isinstance(t, Enum):
        return t.enums[-1]
    if isinstance(t, Boolean):
        return True
    if isinstance(t, Integer):
        return 40 + i
    if isinstance(t, Float):
        return 1234.56 + i
    if isinstance(t, DateTime):
        return datetime.datetime(2026, 3, 11, 21, 59, 8, 604597)
    if isinstance(t, Date):
        return datetime.date(2026, 9, 26)
    if isinstance(t, JSON):
        return {"cliente": "Municipalidad de Alajuela", "items": [1, 2.5, "ñandú"], "vacío": None}
    if isinstance(t, (String, Text)):
        value = f"Árbol ñ {column.name} {i}"
        return value[: t.length] if getattr(t, "length", None) else value
    raise AssertionError(f"unhandled type {t!r} for {column}")


@pytest.fixture
def source_sqlite(tmp_path):
    path = tmp_path / "origen.db"
    engine = create_engine(f"sqlite:///{path}")
    Base.metadata.create_all(engine)
    with engine.begin() as conn:
        for table in Base.metadata.sorted_tables:
            rows = [{c.name: sample_value(c, i) for c in table.columns} for i in range(1, ROWS_PER_TABLE + 1)]
            conn.execute(table.insert(), rows)
        # Rows written by SQLite's CURRENT_TIMESTAMP default have no microseconds.
        conn.execute(text("UPDATE projects SET created_at = '2026-01-13 21:43:25' WHERE id = 1"))
    engine.dispose()
    return str(path)


@pytest.fixture
def target():
    engine = create_engine(PG_URL)
    Base.metadata.drop_all(engine)
    with engine.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS alembic_version"))
    Base.metadata.create_all(engine)
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE alembic_version (version_num VARCHAR(32) PRIMARY KEY)"))
        conn.execute(text("INSERT INTO alembic_version VALUES ('0001')"))
    yield engine
    Base.metadata.drop_all(engine)
    engine.dispose()


def counts(engine):
    with engine.connect() as conn:
        return {t.name: conn.execute(select(func.count()).select_from(t)).scalar() for t in Base.metadata.sorted_tables}


def test_copies_every_table_and_row(source_sqlite, target):
    report = copy(source_sqlite, PG_URL, dry_run=False)
    assert len(report) == len(Base.metadata.tables) == 27
    assert set(counts(target).values()) == {ROWS_PER_TABLE}


def test_values_survive_the_copy(source_sqlite, target):
    copy(source_sqlite, PG_URL, dry_run=False)
    with target.connect() as conn:
        quote = conn.execute(text("select cliente_datos, created_at from quotes where id = 1")).one()
        assert quote.cliente_datos["items"] == [1, 2.5, "ñandú"]
        created = conn.execute(text("select created_at at time zone 'UTC' from projects where id = 1")).scalar()
        assert created == datetime.datetime(2026, 1, 13, 21, 43, 25)
        assert conn.execute(text("select status from invoices where id = 1")).scalar() == "PARTIAL"
        assert conn.execute(text("select is_active from projects where id = 2")).scalar() is None


def test_sequences_continue_after_copied_ids(source_sqlite, target):
    copy(source_sqlite, PG_URL, dry_run=False)
    with target.begin() as conn:
        new_id = conn.execute(User.__table__.insert().values(username="nuevo", hashed_password="x")
                              .returning(User.__table__.c.id)).scalar()
    assert new_id == ROWS_PER_TABLE + 1


def test_dry_run_writes_nothing(source_sqlite, target):
    report = copy(source_sqlite, PG_URL, dry_run=True)
    assert len(report) == 27
    assert set(counts(target).values()) == {0}


def test_refuses_a_target_with_data(source_sqlite, target):
    copy(source_sqlite, PG_URL, dry_run=False)
    with pytest.raises(CopyError, match="ya tiene datos"):
        copy(source_sqlite, PG_URL, dry_run=False)


def test_value_too_long_aborts_everything(source_sqlite, target):
    engine = create_engine(f"sqlite:///{source_sqlite}")
    with engine.begin() as conn:
        conn.execute(text("UPDATE users SET role = 'un-rol-demasiado-largo-para-la-columna' WHERE id = 2"))
    engine.dispose()
    with pytest.raises(CopyError, match="users.role"):
        copy(source_sqlite, PG_URL, dry_run=False)
    assert set(counts(target).values()) == {0}


def test_refuses_sqlite_target(source_sqlite, tmp_path):
    with pytest.raises(CopyError, match="PostgreSQL"):
        copy(source_sqlite, f"sqlite:///{tmp_path / 'destino.db'}", dry_run=False)
