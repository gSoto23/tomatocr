
from sqlalchemy import Column, Integer, String, Boolean, ForeignKey
from sqlalchemy.orm import relationship
from app.db.base import Base

class ProjectSupply(Base):
    __tablename__ = "project_supplies"

    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False)
    name = Column(String(100), nullable=False)
    quantity = Column(String(50)) # String to allow units like "5 kg" or just text

    project = relationship("Project", backref="supplies")

class ProjectTask(Base):
    __tablename__ = "project_tasks"

    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False)
    description = Column(String(255), nullable=False)
    is_required = Column(Boolean, default=True)

    project = relationship("Project", backref="tasks")
