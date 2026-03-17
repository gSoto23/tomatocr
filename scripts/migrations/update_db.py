
import sys
import os
from sqlalchemy import text

# Add app to path
sys.path.append(os.getcwd())

from app.db.session import SessionLocal, engine

def run_migrations():
    print("Running manual migrations for Payroll Module...")
    db = SessionLocal()
    try:
        # 1. Update project_schedules
        print("Checking project_schedules table...")
        try:
            db.execute(text("ALTER TABLE project_schedules ADD COLUMN hours_worked FLOAT DEFAULT 8.0"))
            print("Added hours_worked column.")
        except Exception as e:
            print(f"Column hours_worked might already exist: {e}")

        try:
            db.execute(text("ALTER TABLE project_schedules ADD COLUMN is_confirmed BOOLEAN DEFAULT 0"))
            print("Added is_confirmed column.")
        except Exception as e:
            print(f"Column is_confirmed might already exist: {e}")

        # 2. Update users
        print("Checking users table...")
        columns_to_add = [
            ("phone", "VARCHAR(20)"),
            ("email", "VARCHAR(100)"),
            ("start_date", "DATE"),
            ("hourly_rate", "FLOAT DEFAULT 0.0"),
            ("monthly_salary", "FLOAT DEFAULT 0.0"),
            ("status", "VARCHAR(20) DEFAULT 'active'") 
        ]
        
        for col_name, col_type in columns_to_add:
            try:
                db.execute(text(f"ALTER TABLE users ADD COLUMN {col_name} {col_type}"))
                print(f"Added {col_name} column.")
            except Exception as e:
                print(f"Column {col_name} might already exist: {e}")
        
        db.commit()
        print("Migrations finished.")

    except Exception as e:
        print(f"Migration failed: {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    run_migrations()
