
from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from app.db.base_class import Base

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
    # Set when a task that reports already use is removed from the project: it no
    # longer appears in forms, but old reports keep showing it (migration 0008).
    archived_at = Column(DateTime, nullable=True)

    project = relationship("Project", back_populates="all_tasks")

class ProjectContact(Base):
    __tablename__ = "project_contacts"
    
    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False)
    name = Column(String(100), nullable=False)
    phone = Column(String(20))
    email = Column(String(100))
    position = Column(String(100))
    
    project = relationship("Project", back_populates="contacts")

class ProjectLocation(Base):
    __tablename__ = "project_locations"
    
    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False)
    name = Column(String(100), nullable=False)
    location = Column(String(255))
    waze_pin = Column(String(500))
    # Same as ProjectTask.archived_at, for sedes used by reports or calendar entries.
    archived_at = Column(DateTime, nullable=True)

    project = relationship("Project", back_populates="all_locations")
