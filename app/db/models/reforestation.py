from sqlalchemy import Column, Integer, String, Float, ForeignKey, Date, DateTime
from sqlalchemy.orm import relationship
from datetime import datetime
from app.db.base_class import Base

class ReforestationProject(Base):
    __tablename__ = "reforestation_projects"
    
    id = Column(Integer, primary_key=True, index=True)
    client_name = Column(String(255), index=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    trees = relationship("ReforestationTree", back_populates="project", cascade="all, delete-orphan")


class ReforestationTree(Base):
    __tablename__ = "reforestation_trees"
    
    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey("reforestation_projects.id"))
    tree_number = Column(Integer, index=True)
    species = Column(String(255))
    lat = Column(Float)
    lng = Column(Float)
    sector_name = Column(String(255))
    date_planted = Column(Date, nullable=True)
    
    project = relationship("ReforestationProject", back_populates="trees")
