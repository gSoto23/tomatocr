
from sqlalchemy import Column, Integer, String, Float, Date, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.db.base_class import Base

class PayrollPayment(Base):
    __tablename__ = "payroll_payments"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    amount = Column(Float, nullable=False)
    hours_paid = Column(Float, default=0.0)
    overtime_hours = Column(Float, default=0.0)
    date = Column(Date, nullable=False)
    notes = Column(String(255), nullable=True)
    method = Column(String(30), nullable=True)      # Sinpe, Transferencia, Efectivo
    reference = Column(String(100), nullable=True)  # receipt or transfer number
    payroll_period_id = Column(Integer, ForeignKey("payroll_periods.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    created_by_id = Column(Integer, ForeignKey("users.id"), nullable=True)

    user = relationship("User", foreign_keys=[user_id])
    created_by = relationship("User", foreign_keys=[created_by_id])
    period = relationship("PayrollPeriod")
