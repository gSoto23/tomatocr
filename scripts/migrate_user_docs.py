from app.db.session import engine
from app.db.base import Base

def run_migration():
    print("Conectando con DB y creando tabla user_documents...")
    Base.metadata.create_all(bind=engine)
    print("Migración completada. Tabla user_documents creada exitosamente.")

if __name__ == "__main__":
    run_migration()
