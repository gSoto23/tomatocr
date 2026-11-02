
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
    # Paid outside the system (no payments recorded here): who said so and when. It counts as Pagada.
    paid_outside_at = Column(DateTime(timezone=True), nullable=True)
    paid_outside_by_id = Column(Integer, ForeignKey("users.id"), nullable=True)

    entries = relationship("PayrollEntry", back_populates="period", cascade="all, delete-orphan")
    paid_outside_by = relationship("User", foreign_keys=[paid_outside_by_id])

class PayrollEntry(Base):
    __tablename__ = "payroll_entries"

    id = Column(Integer, primary_key=True, index=True)
    payroll_period_id = Column(Integer, ForeignKey("payroll_periods.id"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    
    total_hours = Column(Float, default=0.0)
    overtime_hours = Column(Float, default=0.0)
    gross_salary = Column(Float, default=0.0)
    social_charges = Column(Float, default=0.0)
    net_salary = Column(Float, default=0.0)
    apply_deductions = Column(Boolean, default=True)
    # Rate used when the payroll was generated (later rate changes do not touch it).
    hourly_rate = Column(Float, nullable=True)
    # How it was paid when generated: hora, dia or mensual (older entries: None = hora).
    pay_type = Column(String(10), nullable=True)
    days_worked = Column(Float, nullable=True)
    # Salary from hours, days or the month (rounded), before lines; gross = base + lines that are salary.
    base_salary = Column(Float, nullable=True)
    details = Column(JSON, nullable=True) # Breakdown

    period = relationship("PayrollPeriod", back_populates="entries")
    user = relationship("User")
    lines = relationship("PayrollLine", back_populates="entry", cascade="all, delete-orphan",
                         order_by="PayrollLine.id")


class PayrollLine(Base):
    """A bono, comisión, ajuste, viáticos, deducción or adelanto on one person's payroll entry
    (app/utils/planilla.py LINE_KINDS says how each one counts)."""
    __tablename__ = "payroll_lines"

    id = Column(Integer, primary_key=True, index=True)
    entry_id = Column(Integer, ForeignKey("payroll_entries.id", ondelete="CASCADE"), nullable=False, index=True)
    kind = Column(String(20), nullable=False)
    description = Column(String(200), nullable=False)
    amount = Column(Float, nullable=False)
    # Set when the line comes from an adjustment left for the next payroll.
    adjustment_id = Column(Integer, ForeignKey("payroll_adjustments.id", ondelete="SET NULL"), nullable=True)
    created_by_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    entry = relationship("PayrollEntry", back_populates="lines")
    adjustment = relationship("PayrollAdjustment", back_populates="lines")


class PayrollAdjustment(Base):
    """A correction for a payroll already approved: it waits here and becomes a line of the
    person's next generated payroll (pending while no line points to it)."""
    __tablename__ = "payroll_adjustments"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    kind = Column(String(20), nullable=False)
    description = Column(String(200), nullable=False)
    amount = Column(Float, nullable=False)
    source_period_id = Column(Integer, ForeignKey("payroll_periods.id", ondelete="SET NULL"), nullable=True)
    created_by_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    user = relationship("User", foreign_keys=[user_id])
    created_by = relationship("User", foreign_keys=[created_by_id])
    source_period = relationship("PayrollPeriod")
    lines = relationship("PayrollLine", back_populates="adjustment")
