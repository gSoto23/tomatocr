
from sqlalchemy import Column, Integer, Date, DateTime, ForeignKey, String, Boolean, Float
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.db.base_class import Base

class ProjectSchedule(Base):
    __tablename__ = "project_schedules"

    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    date = Column(Date, nullable=False, index=True)
    hours_worked = Column(Float, default=8.0)
    overtime_hours = Column(Float, default=0.0)
    is_confirmed = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    project = relationship("Project")
    user = relationship("User")
    tasks = relationship("ScheduleTask", back_populates="schedule", cascade="all, delete-orphan")

class ScheduleTask(Base):
    __tablename__ = "schedule_tasks"

    id = Column(Integer, primary_key=True, index=True)
    schedule_id = Column(Integer, ForeignKey("project_schedules.id"), nullable=False)
    title = Column(String(100), nullable=True)
    description = Column(String(255), nullable=False)
    completed = Column(Boolean, default=False)

    schedule = relationship("ProjectSchedule", back_populates="tasks")
