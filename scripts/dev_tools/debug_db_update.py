
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.db.base import Base
from app.db.models.payroll import PayrollEntry

# Use direct SQLite URL as assumed
SQLALCHEMY_DATABASE_URI = "sqlite:///./sql_app.db"

engine = create_engine(
    SQLALCHEMY_DATABASE_URI,
    connect_args={"check_same_thread": False}
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def debug_persistence():
    db = SessionLocal()
    print("Checking for existing payroll entries...")
    entries = db.query(PayrollEntry).all()
    if not entries:
        print("No payroll entries found. Please generate a payroll first.")
        return

    entry = entries[0]
    print(f"Selected Entry ID: {entry.id}")
    print(f"Current apply_deductions: {entry.apply_deductions}")
    
    # Toggle it
    new_val = not entry.apply_deductions
    print(f"Setting to: {new_val}")
    entry.apply_deductions = new_val
    db.commit()
    
    # Reload
    db.refresh(entry)
    print(f"After commit & refresh: {entry.apply_deductions}")
    
    if entry.apply_deductions == new_val:
        print("SUCCESS: Database update persisted.")
    else:
        print("FAILURE: Database update did NOT persist.")
        
    # Revert
    entry.apply_deductions = not new_val
    db.commit()

if __name__ == "__main__":
    debug_persistence()
