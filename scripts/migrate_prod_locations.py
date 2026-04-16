import sys
import os

# Add the app directory to the python path so we can import app modules
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.db.session import engine
from app.db.base import Base

def run_prod_migration():
    print(f"Connecting to database: {engine.url}")
    
    # 1. Create table project_locations using SQLAlchemy metadata
    # This automatically detects if we need to create it and ignores it if it exists (for most dials)
    # Actually, we can just say Base.metadata.create_all(bind=engine)
    print("Creating new tables generated into Base...")
    Base.metadata.create_all(bind=engine)
    
    # 2. Alter tables to add location_id
    with engine.begin() as conn:
        from sqlalchemy import text
        
        # Determine syntax based on dialect
        if engine.name == 'sqlite':
            daily_log_alter = "ALTER TABLE daily_logs ADD COLUMN location_id INTEGER REFERENCES project_locations(id)"
            schedule_alter = "ALTER TABLE project_schedules ADD COLUMN location_id INTEGER REFERENCES project_locations(id)"
        else: # postgresql
            daily_log_alter = "ALTER TABLE daily_logs ADD COLUMN IF NOT EXISTS location_id INTEGER REFERENCES project_locations(id)"
            schedule_alter = "ALTER TABLE project_schedules ADD COLUMN IF NOT EXISTS location_id INTEGER REFERENCES project_locations(id)"
            
        try:
            conn.execute(text(daily_log_alter))
            print("Successfully added location_id to daily_logs.")
        except Exception as e:
            print(f"Daily logs alter error: {e}")
            
        try:
            conn.execute(text(schedule_alter))
            print("Successfully added location_id to project_schedules.")
        except Exception as e:
            print(f"Project_schedules alter error: {e}")

    print("Production migration complete.")

if __name__ == "__main__":
    run_prod_migration()
