import sqlite3

def run_migration():
    conn = sqlite3.connect('sql_app.db')
    cursor = conn.cursor()
    
    # 1. Create project_locations table
    try:
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS project_locations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER NOT NULL,
            name VARCHAR(100) NOT NULL,
            location VARCHAR(255),
            waze_pin VARCHAR(500),
            FOREIGN KEY(project_id) REFERENCES projects(id)
        )
        ''')
        print("Created project_locations table.")
    except Exception as e:
        print(f"Error creating table: {e}")

    # 2. Add location_id to daily_logs
    try:
        cursor.execute('ALTER TABLE daily_logs ADD COLUMN location_id INTEGER REFERENCES project_locations(id)')
        print("Added location_id to daily_logs.")
    except Exception as e:
        print(f"Daily logs alter error (may already exist): {e}")

    # 3. Add location_id to project_schedules
    try:
        cursor.execute('ALTER TABLE project_schedules ADD COLUMN location_id INTEGER REFERENCES project_locations(id)')
        print("Added location_id to project_schedules.")
    except Exception as e:
        print(f"Project_schedules alter error (may already exist): {e}")
        
    conn.commit()
    conn.close()
    print("Migration complete.")

if __name__ == "__main__":
    run_migration()
