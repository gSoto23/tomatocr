from app.db.session import engine
from sqlalchemy import text

def update_budget_schema():
    with engine.connect() as conn:
        print("Checking project_budgets table schema...")
        result = conn.execute(text("PRAGMA table_info(project_budgets)"))
        columns = [row[1] for row in result.fetchall()]
        print(f"Current columns: {columns}")

        if 'start_date' not in columns:
            print("Adding start_date...")
            conn.execute(text("ALTER TABLE project_budgets ADD COLUMN start_date DATE"))
        
        if 'end_date' not in columns:
            print("Adding end_date...")
            conn.execute(text("ALTER TABLE project_budgets ADD COLUMN end_date DATE"))

        if 'active_prorogue' not in columns:
            print("Adding active_prorogue...")
            conn.execute(text("ALTER TABLE project_budgets ADD COLUMN active_prorogue BOOLEAN DEFAULT 0"))

        print("Schema updated successfully.")

if __name__ == "__main__":
    update_budget_schema()
