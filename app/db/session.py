
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.core.config import settings

# MySQL requires specific connection arguments sometimes, but usually standard is fine with connector
# pool_pre_ping=True helps verify connections before using them
engine = create_engine(
    settings.SQLALCHEMY_DATABASE_URI,
    # The managed PostgreSQL can close idle connections; check each one before use.
    pool_pre_ping=not settings.USE_SQLITE,
    connect_args={"check_same_thread": False} if settings.USE_SQLITE else {}
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
