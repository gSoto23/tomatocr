
import sys
import os

sys.path.append(os.getcwd())

from app.db.session import engine
from app.db.base import Base # Imports all models so they are registered

def create_tables():
    print("Creating all tables...")
    Base.metadata.create_all(bind=engine)
    print("Tables created.")

if __name__ == "__main__":
    create_tables()
