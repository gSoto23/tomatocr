from app.db.base import Base
from app.db.session import engine
from app.db.models.schedule import ScheduleTask

# Create tables
print("Updating database schema...")
Base.metadata.create_all(bind=engine)
print("Database schema updated.")
