
import sys
import os
from sqlalchemy import text

# Add app to path
sys.path.append(os.getcwd())

from app.db.session import SessionLocal

def run_migrations():
    print("Running overtime migration...")
    db = SessionLocal()
    try:
        # 1. Update project_schedules
        try:
            db.execute(text("ALTER TABLE project_schedules ADD COLUMN overtime_hours FLOAT DEFAULT 0.0"))
            print("Added overtime_hours to project_schedules.")
        except Exception as e:
            print(f"project_schedules update skipped: {e}")

        # 2. Update payroll_entries
        try:
            db.execute(text("ALTER TABLE payroll_entries ADD COLUMN overtime_hours FLOAT DEFAULT 0.0"))
            print("Added overtime_hours to payroll_entries.")
        except Exception as e:
            print(f"payroll_entries update skipped: {e}")

        db.commit()
        print("Done.")

    except Exception as e:
        print(f"Migration failed: {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    run_migrations()
