from sqlalchemy import Column, Integer, String, Float, ForeignKey, Date, DateTime, Boolean, Text, UniqueConstraint, text
from sqlalchemy.orm import relationship
from datetime import datetime
from app.db.base_class import Base

# Project kinds. Every project here is "institucional" (public contracts shown on
# the tomatocr.com map). Dárboles trees live on darboles.com, an independent
# platform, so "darboles" is not offered in the admin form; the column stays so
# the public map can keep filtering on it without a migration.
KIND_INSTITUCIONAL = "institucional"
KIND_DARBOLES = "darboles"
PROJECT_KINDS = (KIND_INSTITUCIONAL, KIND_DARBOLES)

STATUS_UNVERIFIED = "sin_verificar"
STATUS_ALIVE = "vivo"
STATUS_DEAD = "muerto"
STATUS_REPLACED = "reemplazado"
TREE_STATUSES = (STATUS_UNVERIFIED, STATUS_ALIVE, STATUS_DEAD, STATUS_REPLACED)
# Statuses a monitoring check can record.
CHECK_STATUSES = (STATUS_ALIVE, STATUS_DEAD, STATUS_REPLACED)


class ReforestationProject(Base):
    __tablename__ = "reforestation_projects"

    id = Column(Integer, primary_key=True, index=True)
    client_name = Column(String(255), index=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    project_id = Column(Integer, ForeignKey("projects.id"), nullable=True)
    kind = Column(String(20), nullable=False, default=KIND_INSTITUCIONAL, server_default=KIND_INSTITUCIONAL)
    # is_public: the client authorized showing public_name on the public map.
    # Without it the map shows "Proyecto institucional".
    is_public = Column(Boolean, nullable=False, default=False, server_default=text("false"))
    public_name = Column(String(255), nullable=True)
    consent_date = Column(Date, nullable=True)

    trees = relationship("ReforestationTree", back_populates="project", cascade="all, delete-orphan")
    project = relationship("Project")


class ReforestationTree(Base):
    __tablename__ = "reforestation_trees"
    __table_args__ = (
        UniqueConstraint("project_id", "tree_number", name="uq_reforestation_trees_project_number"),
    )

    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey("reforestation_projects.id"))
    tree_number = Column(Integer, index=True)
    species = Column(String(255))
    lat = Column(Float)
    lng = Column(Float)
    sector_name = Column(String(255))
    date_planted = Column(Date, nullable=True)

    status = Column(String(20), nullable=False, default=STATUS_UNVERIFIED, server_default=STATUS_UNVERIFIED)
    last_checked_at = Column(Date, nullable=True)
    # Set on a dead tree that was replaced: points to the new tree.
    replaced_by_id = Column(Integer, ForeignKey("reforestation_trees.id"), nullable=True)

    project = relationship("ReforestationProject", back_populates="trees")
    checks = relationship("TreeCheck", back_populates="tree", cascade="all, delete-orphan",
                          order_by="TreeCheck.checked_at")
    replaced_by = relationship("ReforestationTree", remote_side=[id], foreign_keys=[replaced_by_id])


class TreeCheck(Base):
    """One monitoring observation of a tree."""
    __tablename__ = "tree_checks"

    id = Column(Integer, primary_key=True, index=True)
    tree_id = Column(Integer, ForeignKey("reforestation_trees.id", ondelete="CASCADE"), nullable=False, index=True)
    checked_at = Column(Date, nullable=False)
    status = Column(String(20), nullable=False)
    height_cm = Column(Float, nullable=True)
    notes = Column(Text, nullable=True)
    photo_path = Column(String(500), nullable=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    daily_log_id = Column(Integer, ForeignKey("daily_logs.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    tree = relationship("ReforestationTree", back_populates="checks")
    user = relationship("User")
