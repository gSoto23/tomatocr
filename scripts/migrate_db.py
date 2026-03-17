import os
import sys

# Fix relative imports when executing outside Uvicorn (from root folder)
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine
from sqlalchemy.exc import OperationalError
from app.core.config import settings
from app.db.base import Base

def migrate():
    # Force the local DB uri (SQLite or MySQL if defined in ENV)
    # Search for the SQLite file in root first since it's the actual production DB
    default_sqlite_path = "sqlite:///sql_app.db" if os.path.exists(os.path.join(os.getcwd(), "sql_app.db")) else "sqlite:///app/sql_app.db"
    sqlite_uri = os.getenv("SOURCE_DB_URI", default_sqlite_path)
    pg_uri = settings.SQLALCHEMY_DATABASE_URI
    
    # Make sure we don't accidentally wipe Postgres reading from itself
    if "sqlite" in pg_uri:
        print("ERROR: Environment is claiming to use SQLite. Ensure USE_SQLITE=False and AWS variables are mapped.")
        return

    print(f"Migrating Local SQLite to Remote PostgreSQL...")
    print(f"Remote Server: {settings.DB_SERVER}")

    sqlite_engine = create_engine(sqlite_uri)
    pg_engine = create_engine(pg_uri)
    
    # Initialize Schema on PostgreSQL
    print("Building schema in PostgreSQL...")
    Base.metadata.create_all(bind=pg_engine)
    
    with pg_engine.begin() as pg_conn:
        with sqlite_engine.begin() as sq_conn:
            # Disable FK checks temporally during migration if needed, but sorted_tables respects dependencies
            for table in Base.metadata.sorted_tables:
                print(f"Migrating table: {table.name}...")
                
                # We pull from local SQLite via the app schemas Context
                try:
                    result = sq_conn.execute(table.select())
                    rows = result.mappings().all()
                except OperationalError as e:
                    if "no such table" in str(e).lower():
                        print(f"  -> Skipping table '{table.name}' (does not exist in source DB).")
                        continue
                    raise e
                
                if rows:
                    # Postgres does not tolerate Integer 1/0 for Booleans easily if the mapped dict bypasses type coercion.
                    # We'll explicitly massage the dictionaries just in case.
                    clean_rows = []
                    for row in rows:
                        clean_row = dict(row)
                        for col in table.columns:
                            # If column is boolean and value is integer 1/0, map it to True/False
                            if str(col.type) == 'BOOLEAN' and clean_row[col.name] is not None:
                                clean_row[col.name] = bool(clean_row[col.name])
                        clean_rows.append(clean_row)

                    # Delete existing to prevent Primary Key Collisions
                    pg_conn.execute(table.delete())
                    pg_conn.execute(table.insert(), clean_rows)
                    print(f"  -> Inserted {len(clean_rows)} rows.")
                else:
                    print(f"  -> 0 rows.")

    print("Success! Data Migration Completed.")

if __name__ == "__main__":
    migrate()
