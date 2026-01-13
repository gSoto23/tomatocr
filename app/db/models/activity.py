from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, JSON
from sqlalchemy.orm import relationship
from datetime import datetime

from app.db.base_class import Base

class ActivityLog(Base):
    __tablename__ = "activity_logs"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    action = Column(String(50)) # CREATE, UPDATE, DELETE, LOGIN, ETC
    entity_type = Column(String(50)) # PROJECT, USER, LOG, SCHEDULE
    entity_id = Column(Integer, nullable=True) # ID of the affected object
    details = Column(Text, nullable=True) # JSON or String details
    ip_address = Column(String(50), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", backref="activities")
