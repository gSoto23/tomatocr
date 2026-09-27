from sqlalchemy import Column, Integer, String, Boolean, DateTime, Index
from datetime import datetime

from app.db.base_class import Base

class LoginAttempt(Base):
    __tablename__ = "login_attempts"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(50), nullable=False)
    ip_address = Column(String(50), nullable=True)
    success = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    __table_args__ = (
        Index("ix_login_attempts_username_created_at", "username", "created_at"),
        Index("ix_login_attempts_ip_created_at", "ip_address", "created_at"),
    )
