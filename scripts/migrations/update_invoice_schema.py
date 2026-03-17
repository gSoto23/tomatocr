import sqlite3

# Connect to the SQLite database
conn = sqlite3.connect("sql_app.db")
cursor = conn.cursor()

try:
    # Add 'note' column to invoices table
    print("Adding 'note' column to invoices table...")
    cursor.execute("ALTER TABLE invoices ADD COLUMN note TEXT")
    print("Column 'note' added successfully.")
except sqlite3.OperationalError as e:
    if "duplicate column" in str(e).lower():
        print("Column 'note' already exists, skipping.")
    else:
        print(f"Error adding 'note' column: {e}")

conn.commit()
conn.close()
