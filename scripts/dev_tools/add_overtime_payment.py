
import sys
import os
from sqlalchemy import create_engine, text

# Add current directory to path
sys.path.append(os.getcwd())

from app.core.config import settings

def run_migration():
    print(f"Connecting to database: {settings.SQLALCHEMY_DATABASE_URI}")
    engine = create_engine(settings.SQLALCHEMY_DATABASE_URI)
    
    with engine.connect() as connection:
        # Check if column exists
        try:
            # SQLite check
            result = connection.execute(text("PRAGMA table_info(payroll_payments)"))
            columns = [row[1] for row in result.fetchall()]
            if 'overtime_hours' in columns:
                print("Column 'overtime_hours' already exists.")
                return
        except Exception as e:
            print(f"Warning checking columns: {e}")

        # Add column
        try:
            print("Adding column 'overtime_hours' to payroll_payments...")
            connection.execute(text("ALTER TABLE payroll_payments ADD COLUMN overtime_hours FLOAT DEFAULT 0.0"))
            print("Column added successfully.")
        except Exception as e:
            print(f"Error adding column: {e}")

if __name__ == "__main__":
    run_migration()
