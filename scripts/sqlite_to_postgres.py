"""Copy all data from the production SQLite file into an empty PostgreSQL.

The target must already have the schema from Alembic (`alembic upgrade head`)
and no rows. Every table is copied in foreign-key order keeping its ids, the
id sequences are moved past the copied rows, and each table is compared row by
row against the source before committing. Anything unexpected aborts the whole
copy: nothing is written unless every check passes.

Usage (from the project root, with the target DB_* variables in the
environment or .env and USE_SQLITE="False"):

    PYTHONPATH=. python scripts/sqlite_to_postgres.py --sqlite sql_app.db --dry-run
    PYTHONPATH=. python scripts/sqlite_to_postgres.py --sqlite sql_app.db

--dry-run performs the full copy and all checks inside a transaction and then
rolls it back.
"""
import argparse
import datetime
import enum
import sys
from pathlib import Path

from sqlalchemy import Enum, String, create_engine, func, inspect, select, text

from app.core.config import settings
from app.db.base import Base

BATCH_SIZE = 500


class CopyError(Exception):
    pass


def alembic_head() -> str:
    """Latest migration in alembic/versions: the schema the models describe."""
    from alembic.config import Config
    from alembic.script import ScriptDirectory
    root = Path(__file__).resolve().parent.parent
    config = Config(str(root / "alembic.ini"))
    config.set_main_option("script_location", str(root / "alembic"))
    return ScriptDirectory.from_config(config).get_current_head()


def normalize(value):
    """Makes source (SQLite) and target (PostgreSQL) values comparable."""
    if isinstance(value, datetime.datetime) and value.tzinfo is not None:
        return value.astimezone(datetime.timezone.utc).replace(tzinfo=None)
    if isinstance(value, enum.Enum):
        return value.name
    return value


def read_rows(conn, table):
    pk = list(table.primary_key.columns)
    return [dict(row._mapping) for row in conn.execute(select(table).order_by(*pk))]


def check_lengths(table, rows):
    """SQLite ignores VARCHAR(n); PostgreSQL rejects longer values."""
    problems = []
    for column in table.columns:
        # Enum subclasses String, but PostgreSQL validates enum values itself.
        if isinstance(column.type, String) and not isinstance(column.type, Enum) and column.type.length:
            for row in rows:
                value = row[column.name]
                if isinstance(value, str) and len(value) > column.type.length:
                    problems.append(f"{table.name}.{column.name} id={row.get('id')}: "
                                    f"{len(value)} caracteres, máximo {column.type.length}")
    return problems


def check_source_schema(source_engine):
    insp = inspect(source_engine)
    source_tables = set(insp.get_table_names())
    model_tables = set(Base.metadata.tables)
    problems = []
    if source_tables != model_tables:
        problems.append(f"tablas distintas: solo en SQLite {sorted(source_tables - model_tables)}, "
                        f"solo en modelos {sorted(model_tables - source_tables)}")
    for name in sorted(source_tables & model_tables):
        source_cols = {c["name"] for c in insp.get_columns(name)}
        model_cols = set(Base.metadata.tables[name].columns.keys())
        if source_cols != model_cols:
            problems.append(f"{name}: columnas solo en SQLite {sorted(source_cols - model_cols)}, "
                            f"solo en modelos {sorted(model_cols - source_cols)}")
    return problems


def check_target_ready(conn):
    insp = inspect(conn)
    if "alembic_version" not in insp.get_table_names():
        raise CopyError("La base destino no tiene alembic_version. Corré primero: alembic upgrade head")
    version = conn.execute(text("select version_num from alembic_version")).scalar()
    head = alembic_head()
    if version != head:
        raise CopyError(f"La base destino está en la versión {version}; el código espera {head}. "
                        "Corré: alembic upgrade head")
    not_empty = [t.name for t in Base.metadata.sorted_tables
                 if conn.execute(select(func.count()).select_from(t)).scalar()]
    if not_empty:
        raise CopyError(f"La base destino ya tiene datos en: {', '.join(not_empty)}")


def copy(sqlite_path, target_url, dry_run):
    source_engine = create_engine(f"sqlite:///file:{sqlite_path}?mode=ro&uri=true")
    target_engine = create_engine(target_url)
    if target_engine.dialect.name != "postgresql":
        raise CopyError(f"El destino debe ser PostgreSQL, no {target_engine.dialect.name}. "
                        "Revisá USE_SQLITE y DB_* en el entorno.")

    problems = check_source_schema(source_engine)
    if problems:
        raise CopyError("El esquema del SQLite no coincide con los modelos:\n  " + "\n  ".join(problems))

    report = []
    with source_engine.connect() as source, target_engine.connect() as target:
        transaction = target.begin()
        try:
            # Naive datetimes from SQLite are UTC; store them as such in timestamptz columns.
            target.execute(text("SET LOCAL TIME ZONE 'UTC'"))
            check_target_ready(target)
            for table in Base.metadata.sorted_tables:
                rows = read_rows(source, table)
                problems = check_lengths(table, rows)
                if problems:
                    raise CopyError("Valores más largos de lo permitido:\n  " + "\n  ".join(problems))
                for start in range(0, len(rows), BATCH_SIZE):
                    target.execute(table.insert(), rows[start:start + BATCH_SIZE])

                copied = read_rows(target, table)
                if len(copied) != len(rows):
                    raise CopyError(f"{table.name}: {len(rows)} filas en SQLite, {len(copied)} en PostgreSQL")
                for original, new in zip(rows, copied):
                    for key in original:
                        if normalize(original[key]) != normalize(new[key]):
                            raise CopyError(f"{table.name} id={original.get('id')}: {key} "
                                            f"{original[key]!r} se copió como {new[key]!r}")

                if "id" in table.columns and table.columns["id"].autoincrement is not False:
                    target.execute(text(
                        f"SELECT setval(pg_get_serial_sequence('{table.name}', 'id'), "
                        f"COALESCE((SELECT MAX(id) FROM {table.name}), 1), "
                        f"(SELECT MAX(id) FROM {table.name}) IS NOT NULL)"
                    ))
                report.append((table.name, len(rows)))

            if dry_run:
                transaction.rollback()
            else:
                transaction.commit()
        except Exception:
            transaction.rollback()
            raise
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--sqlite", default="sql_app.db", help="archivo SQLite de origen (se abre solo lectura)")
    parser.add_argument("--dry-run", action="store_true", help="copiar y verificar, y luego deshacer todo")
    args = parser.parse_args()

    if settings.USE_SQLITE:
        print("USE_SQLITE es verdadero: el destino sería SQLite. Definí USE_SQLITE=False y las DB_*.", file=sys.stderr)
        return 1

    print(f"Origen:  {args.sqlite}")
    print(f"Destino: {settings.DB_SERVER}/{settings.DB_NAME}")
    try:
        report = copy(args.sqlite, settings.SQLALCHEMY_DATABASE_URI, args.dry_run)
    except CopyError as e:
        print(f"\nERROR, no se copió nada: {e}", file=sys.stderr)
        return 1

    width = max(len(name) for name, _ in report)
    for name, count in report:
        print(f"  {name.ljust(width)}  {count:>6} filas  OK")
    total = sum(count for _, count in report)
    if args.dry_run:
        print(f"\nPrueba completa: {total} filas copiadas y verificadas, y luego deshechas. No se guardó nada.")
    else:
        print(f"\nListo: {total} filas copiadas y verificadas en {len(report)} tablas.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
