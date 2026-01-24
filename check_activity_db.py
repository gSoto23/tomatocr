
import sys
import os
from sqlalchemy import text

# Add app to path
sys.path.append(os.getcwd())

from app.db.session import SessionLocal, engine
from app.db.base import Base
# Make sure models are imported so they are registered
from app.db.models.activity import ActivityLog

def check_activity_log():
    print("Checking ActivityLog table...")
    db = SessionLocal()
    try:
        # Check if table exists by running a simple query
        # This works if the table was created by create_all
        count = db.query(ActivityLog).count()
        print(f"ActivityLog table exists. Count: {count}")
        
        # Try to insert a dummy log if empty? No, just check access.
        
    except Exception as e:
        print(f"Error accessing ActivityLog: {e}")
        # Try to see if we can create it
        print("Attempting to create tables...")
        Base.metadata.create_all(bind=engine)
        print("Tables created.")
        try:
            count = db.query(ActivityLog).count()
            print(f"ActivityLog table exists after creation. Count: {count}")
        except Exception as e2:
            print(f"Still failing: {e2}")
    finally:
        db.close()

if __name__ == "__main__":
    check_activity_log()
