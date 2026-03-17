from app.db.session import SessionLocal
from sqlalchemy import text

def migrate():
    db = SessionLocal()
    try:
        # Check if columns exist (SQLite specific pragma or just try alter and ignore error)
        # Attempting to add columns. If they exist, it might fail, but that's fine for a one-off script.
        
        try:
            db.execute(text("ALTER TABLE users ADD COLUMN payment_method VARCHAR(20) DEFAULT 'Efectivo'"))
            print("Added payment_method column.")
        except Exception as e:
            print(f"payment_method column might already exist: {e}")

        try:
            db.execute(text("ALTER TABLE users ADD COLUMN account_number VARCHAR(50)"))
            print("Added account_number column.")
        except Exception as e:
            print(f"account_number column might already exist: {e}")
            
        db.commit()
    finally:
        db.close()

if __name__ == "__main__":
    migrate()
