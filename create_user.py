
from app.db.session import SessionLocal, engine
from app.db.base import Base
from app.db.models.user import User
from app.db.models.project import Project # Needed for mapper registry
from app.db.models.log import DailyLog # Needed for mapper registry
from app.db.models.schedule import ProjectSchedule # Needed for mapper registry
from app.core.security import get_password_hash

def create_initial_data():
    # Create Tables
    print("Creating tables...")
    Base.metadata.create_all(bind=engine)
    
    db = SessionLocal()

    # Admin User
    admin = db.query(User).filter(User.username == "admin").first()
    if not admin:
        print("Creating admin user...")
        admin = User(
            username="admin",
            hashed_password=get_password_hash("admin123"),
            full_name="Admin User",
            role="admin"
        )
        db.add(admin)
        db.commit()
        print("Admin user created.")
    else:
        print("Admin user already exists.")
    
    # Client User
    client = db.query(User).filter(User.username == "client").first()
    if not client:
        print("Creating client user...")
        client = User(
            username="client",
            hashed_password=get_password_hash("client123"),
            full_name="Test Client",
            role="client"
        )
        db.add(client)
        db.commit()
        print("Client user created.")
    else:
        print("Client user already exists.")

    # Worker User
    worker = db.query(User).filter(User.username == "worker").first()
    if not worker:
        print("Creating worker user...")
        worker = User(
            username="worker",
            hashed_password=get_password_hash("worker123"),
            full_name="Test Worker",
            role="worker"
        )
        db.add(worker)
        db.commit()
        print("Worker user created.")
    else:
        print("Worker user already exists.")

    db.close()

if __name__ == "__main__":
    create_initial_data()
