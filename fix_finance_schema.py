import sqlite3
import datetime

def fix_db():
    conn = sqlite3.connect('sql_app.db')
    cursor = conn.cursor()
    
    try:
        # Check if table exists
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='project_budgets'")
        if not cursor.fetchone():
            print("Table project_budgets does not exist.")
            return

        # Get existing columns
        cursor.execute("PRAGMA table_info(project_budgets)")
        columns = [info[1] for info in cursor.fetchall()]
        print(f"Current columns: {columns}")

        if 'created_at' not in columns:
            print("Adding created_at column...")
            # SQLite limitation: add as nullable first
            cursor.execute("ALTER TABLE project_budgets ADD COLUMN created_at TIMESTAMP")
            
        if 'updated_at' not in columns:
            print("Adding updated_at column...")
            cursor.execute("ALTER TABLE project_budgets ADD COLUMN updated_at TIMESTAMP")

        conn.commit()
        print("Schema update complete.")
        
    except Exception as e:
        print(f"Error: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    fix_db()
