from sqlalchemy import Column, Integer, String, Float, Date, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.db.base_class import Base


class Commission(Base):
    """A seller's commission (docs/PLAN_PLANILLA_CALENDARIO.md, Fase 5): per invoice once it is
    PAGADA (a % of its amount without IVA), or once per new client with its first paid invoice.
    It is paid through a payroll adjustment, so it can be traced to the payroll that paid it."""
    __tablename__ = "commissions"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    kind = Column(String(20), nullable=False)  # factura, cliente_nuevo
    invoice_id = Column(Integer, ForeignKey("invoices.id", ondelete="SET NULL"), nullable=True, index=True)
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="SET NULL"), nullable=True)
    opportunity_id = Column(Integer, ForeignKey("opportunities.id", ondelete="SET NULL"), nullable=True, index=True)
    account_id = Column(Integer, ForeignKey("accounts.id", ondelete="SET NULL"), nullable=True)
    # Kept as text too, so the record still reads well if the invoice or account goes away.
    client_name = Column(String(200), nullable=True)
    invoice_number = Column(String(50), nullable=True)
    payment_date = Column(Date, nullable=True)
    base_amount = Column(Float, nullable=True)   # invoice amount without IVA
    rate = Column(Float, nullable=True)          # % for "factura"
    amount = Column(Float, nullable=False)
    adjustment_id = Column(Integer, ForeignKey("payroll_adjustments.id", ondelete="SET NULL"), nullable=True)
    reversal_adjustment_id = Column(Integer, ForeignKey("payroll_adjustments.id", ondelete="SET NULL"),
                                    nullable=True)
    cancelled_at = Column(DateTime(timezone=True), nullable=True)
    cancel_reason = Column(String(255), nullable=True)
    cancelled_by_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    user = relationship("User", foreign_keys=[user_id])
    cancelled_by = relationship("User", foreign_keys=[cancelled_by_id])
    adjustment = relationship("PayrollAdjustment", foreign_keys=[adjustment_id])
    reversal_adjustment = relationship("PayrollAdjustment", foreign_keys=[reversal_adjustment_id])
