
from sqlalchemy import Column, Integer, String, Float, Date, DateTime, ForeignKey, JSON, Boolean
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.db.base_class import Base

class PayrollPeriod(Base):
    __tablename__ = "payroll_periods"

    id = Column(Integer, primary_key=True, index=True)
    start_date = Column(Date, nullable=False)
    end_date = Column(Date, nullable=False)
    status = Column(String(20), default="draft") # draft, final
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    entries = relationship("PayrollEntry", back_populates="period", cascade="all, delete-orphan")

class PayrollEntry(Base):
    __tablename__ = "payroll_entries"

    id = Column(Integer, primary_key=True, index=True)
    payroll_period_id = Column(Integer, ForeignKey("payroll_periods.id"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    
    total_hours = Column(Float, default=0.0)
    gross_salary = Column(Float, default=0.0)
    social_charges = Column(Float, default=0.0)
    net_salary = Column(Float, default=0.0)
    details = Column(JSON, nullable=True) # Breakdown

    period = relationship("PayrollPeriod", back_populates="entries")
    user = relationship("User")
