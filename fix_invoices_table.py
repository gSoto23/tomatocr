from app.db.session import engine
from sqlalchemy import text

def fix_invoices_table():
    with engine.connect() as conn:
        print("Checking invoices table schema...")
        
        # Check current columns via PRAGMA
        result = conn.execute(text("PRAGMA table_info(invoices)"))
        columns = [row[1] for row in result.fetchall()]
        print(f"Current columns: {columns}")

        # 1. Rename line_id -> budget_line_id
        if 'line_id' in columns:
            print("Renaming line_id to budget_line_id...")
            conn.execute(text("ALTER TABLE invoices RENAME COLUMN line_id TO budget_line_id"))
        
        # 2. Rename date_issued -> issue_date
        if 'date_issued' in columns:
            print("Renaming date_issued to issue_date...")
            conn.execute(text("ALTER TABLE invoices RENAME COLUMN date_issued TO issue_date"))

        # 3. Add status column
        # Re-fetch columns to see if 'status' exists (unlikely given previous check, but safe)
        result = conn.execute(text("PRAGMA table_info(invoices)"))
        columns = [row[1] for row in result.fetchall()]
        
        if 'status' not in columns:
            print("Adding status column...")
            conn.execute(text("ALTER TABLE invoices ADD COLUMN status VARCHAR DEFAULT 'pendiente'"))
            
        if 'created_at' not in columns:
            print("Adding created_at column...")
            conn.execute(text("ALTER TABLE invoices ADD COLUMN created_at DATETIME DEFAULT CURRENT_TIMESTAMP"))
            
        print("Invoices table schema fixed!")

if __name__ == "__main__":
    fix_invoices_table()
