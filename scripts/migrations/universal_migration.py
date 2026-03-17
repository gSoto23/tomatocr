
from sqlalchemy import create_engine, text
from app.core.config import settings
import logging

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def migrate():
    print(f"Connecting to database: {settings.SQLALCHEMY_DATABASE_URI}")
    engine = create_engine(settings.SQLALCHEMY_DATABASE_URI)
    
    with engine.connect() as conn:
        # Check dialect
        dialect = engine.dialect.name
        print(f"Database dialect: {dialect}")
        
        # 1. users table
        try:
            if dialect == "sqlite":
                conn.execute(text("ALTER TABLE users ADD COLUMN apply_deductions BOOLEAN DEFAULT 1"))
            elif dialect == "mysql":
                conn.execute(text("ALTER TABLE users ADD COLUMN apply_deductions BOOLEAN DEFAULT TRUE"))
            else:
                 # Standard SQL fallback
                conn.execute(text("ALTER TABLE users ADD COLUMN apply_deductions BOOLEAN DEFAULT 1"))
            print("Successfully added apply_deductions to users.")
        except Exception as e:
            print(f"Could not alter users (maybe exists?): {e}")

        # 2. payroll_entries table
        try:
            if dialect == "sqlite":
                conn.execute(text("ALTER TABLE payroll_entries ADD COLUMN apply_deductions BOOLEAN DEFAULT 1"))
            elif dialect == "mysql":
                 conn.execute(text("ALTER TABLE payroll_entries ADD COLUMN apply_deductions BOOLEAN DEFAULT TRUE"))
            else:
                conn.execute(text("ALTER TABLE payroll_entries ADD COLUMN apply_deductions BOOLEAN DEFAULT 1"))
            print("Successfully added apply_deductions to payroll_entries.")
        except Exception as e:
            print(f"Could not alter payroll_entries (maybe exists?): {e}")
            
        conn.commit()
    
    print("Migration finished.")

if __name__ == "__main__":
    migrate()
