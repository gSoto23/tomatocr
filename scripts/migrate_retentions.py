import sqlite3
import os

DB_PATH = "sql_app.db"

def apply_migration():
    if not os.path.exists(DB_PATH):
        print(f"Database {DB_PATH} not found.")
        return
        
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    try:
        # Add retention_amount column to payments table
        cursor.execute("ALTER TABLE payments ADD COLUMN retention_amount FLOAT DEFAULT 0.0;")
        conn.commit()
        print("Migration completely successful. Column 'retention_amount' added to 'payments' table.")
    except sqlite3.OperationalError as e:
        if "duplicate column name" in str(e).lower():
            print("Migration already applied. Column 'retention_amount' already exists.")
        else:
            print(f"OperationalError: {e}")
            conn.rollback()
    except Exception as e:
        print(f"Error during migration: {e}")
        conn.rollback()
    finally:
        conn.close()

if __name__ == "__main__":
    apply_migration()
