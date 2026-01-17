
import sqlite3
import os

def migrate():
    db_path = "sql_app.db"
    print(f"Migrating database at {os.path.abspath(db_path)}...")
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Add apply_deductions to users
    try:
        cursor.execute("ALTER TABLE users ADD COLUMN apply_deductions BOOLEAN DEFAULT 1")
        print("Added apply_deductions to users table")
    except sqlite3.OperationalError as e:
        print(f"Skipping users table: {e}")

    # Add apply_deductions to payroll_entries
    try:
        cursor.execute("ALTER TABLE payroll_entries ADD COLUMN apply_deductions BOOLEAN DEFAULT 1")
        print("Added apply_deductions to payroll_entries table")
    except sqlite3.OperationalError as e:
        print(f"Skipping payroll_entries table: {e}")

    conn.commit()
    conn.close()
    print("Migration complete.")

if __name__ == "__main__":
    migrate()
