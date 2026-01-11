
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.core.config import settings

# MySQL requires specific connection arguments sometimes, but usually standard is fine with connector
# pool_pre_ping=True helps verify connections before using them
engine = create_engine(
    settings.SQLALCHEMY_DATABASE_URI,
    # pool_pre_ping=True, # Not needed for SQLite typically
    connect_args={"check_same_thread": False} if settings.USE_SQLITE else {}
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
