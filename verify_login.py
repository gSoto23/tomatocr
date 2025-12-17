
from app.db.session import SessionLocal
from app.db.models.user import User
from app.db.models.project import Project
from app.db.models.log import DailyLog
from app.core.security import verify_password

def verify_login():
    db = SessionLocal()
    user = db.query(User).filter(User.username == "admin").first()
    
    if not user:
        print("User 'admin' does not exist in the database.")
    else:
        print(f"User 'admin' found. Role: {user.role}")
        if verify_password("admin123", user.hashed_password):
            print("Password 'admin123' works!")
        else:
            print("Password 'admin123' invalid.")
            print(f"Hash in DB: {user.hashed_password}")
            
    db.close()

if __name__ == "__main__":
    verify_login()
