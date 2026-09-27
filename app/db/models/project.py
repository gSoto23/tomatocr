
from sqlalchemy import Column, Integer, String, Text, Boolean, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.db.base_class import Base
from app.db.models.associations import project_users

class Project(Base):
    __tablename__ = "projects"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False, index=True)
    location = Column(Text)
    description = Column(Text)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # New Fields
    client_display_name = Column(String(100))
    province = Column(String(50))
    address = Column(Text)
    waze_link = Column(String(500))
    
    contact_name = Column(String(100))
    contact_phone = Column(String(20))
    contact_email = Column(String(100))

    # CRM (docs/DISENO_CRM.md). client_display_name stays as the text shown today.
    account_id = Column(Integer, ForeignKey("accounts.id"), nullable=True, index=True)
    opportunity_id = Column(Integer, ForeignKey("opportunities.id"), nullable=True)

    users = relationship("User", secondary=project_users, back_populates="projects")
    contacts = relationship("ProjectContact", back_populates="project", cascade="all, delete-orphan")
    # Every task and sede, archived ones included; `tasks` and `locations` are the ones in use.
    all_tasks = relationship("ProjectTask", back_populates="project", order_by="ProjectTask.id")
    all_locations = relationship("ProjectLocation", back_populates="project", cascade="all, delete-orphan",
                                 order_by="ProjectLocation.id")
    tasks = relationship("ProjectTask", viewonly=True, order_by="ProjectTask.id",
                         primaryjoin="and_(ProjectTask.project_id == Project.id, ProjectTask.archived_at.is_(None))")
    locations = relationship("ProjectLocation", viewonly=True, order_by="ProjectLocation.id",
                             primaryjoin="and_(ProjectLocation.project_id == Project.id, "
                                         "ProjectLocation.archived_at.is_(None))")
    budget = relationship("ProjectBudget", uselist=False, back_populates="project", cascade="all, delete-orphan")
