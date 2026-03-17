from sqlalchemy import Column, Integer, String, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from datetime import datetime
from app.db.base import Base

class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    action = Column(String, index=True)
    entity_type = Column(String, index=True, nullable=True) # e.g. 'Project', 'DailyLog', 'User'
    entity_id = Column(Integer, nullable=True)
    details = Column(String, nullable=True) # JSON or additional text
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User")
