
from sqlalchemy import Column, Integer, String, Boolean, Enum, Date, Float
from sqlalchemy.orm import relationship
from app.db.base_class import Base
from app.db.models.associations import project_users

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(50), unique=True, index=True, nullable=False)
    hashed_password = Column(String(255), nullable=False)
    full_name = Column(String(100))
    role = Column(String(20), default="worker") # admin, worker, client, supervisor
    is_active = Column(Boolean, default=True)

    # Payroll Fields
    phone = Column(String(20), nullable=True)
    email = Column(String(100), nullable=True)
    start_date = Column(Date, nullable=True)
    hourly_rate = Column(Float, default=0.0)
    monthly_salary = Column(Float, default=0.0) # Informative
    status = Column(Enum("active", "inactive", "liquidated", name="worker_status"), default="active")

    projects = relationship("Project", secondary=project_users, back_populates="users")
