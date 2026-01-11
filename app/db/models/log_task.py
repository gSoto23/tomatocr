
from sqlalchemy import Column, Integer, Boolean, String, ForeignKey
from sqlalchemy.orm import relationship
from app.db.base import Base

class DailyLogTask(Base):
    __tablename__ = "daily_log_tasks"

    id = Column(Integer, primary_key=True, index=True)
    log_id = Column(Integer, ForeignKey("daily_logs.id"), nullable=False)
    task_id = Column(Integer, ForeignKey("project_tasks.id"), nullable=False)
    completed = Column(Boolean, default=False)
    notes = Column(String(255))

    log = relationship("DailyLog", backref="task_entries")
    task = relationship("ProjectTask")
