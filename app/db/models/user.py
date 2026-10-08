
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
    apply_deductions = Column(Boolean, default=True)

    # Payroll Fields
    phone = Column(String(20), nullable=True)
    email = Column(String(100), nullable=True)
    start_date = Column(Date, nullable=True)
    hourly_rate = Column(Float, default=0.0)
    monthly_salary = Column(Float, default=0.0) # Informative
    # Vacation days already taken in the current contract (recorded by the admin).
    vacation_days_taken = Column(Float, nullable=False, default=0.0, server_default="0")
    # A supervisor who also sells: sees Clientes and the Cotizador like ventas ("También vende").
    also_sells = Column(Boolean, nullable=False, default=False, server_default="false")
    status = Column(Enum("active", "inactive", "liquidated", name="worker_status"), default="active")
    
    # Payment Info
    payment_method = Column(String(20), default="Efectivo") # Transferencia, Sinpe, Efectivo
    account_number = Column(String(50), nullable=True)

    projects = relationship("Project", secondary=project_users, back_populates="users")
    documents = relationship("UserDocument", back_populates="user", cascade="all, delete-orphan")

    @property
    def sells(self) -> bool:
        """Works in Clientes and the Cotizador: admin, ventas, and a supervisor marked "También vende"."""
        return self.role in ("admin", "ventas") or (self.role == "supervisor" and bool(self.also_sells))
