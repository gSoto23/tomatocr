from sqlalchemy import Column, Integer, String, Float, Boolean, ForeignKey, Date, Enum, DateTime
from sqlalchemy.orm import relationship, backref
from sqlalchemy.sql import func
import enum
from app.db.base_class import Base

class InvoiceStatus(str, enum.Enum):
    PENDING = "pendiente"
    OVERDUE = "vencida"
    PAID = "pagada"
    PARTIAL = "pago_parcial"

class ProjectBudget(Base):
    __tablename__ = "project_budgets"

    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey("projects.id"), unique=True, nullable=False)
    
    # Licitation Info
    licitation_number = Column(String, nullable=True)
    contract_duration = Column(String, nullable=True) # e.g. "12 months"
    
    # Prorrogable Info
    is_prorrogable = Column(Boolean, default=False)
    prorrogable_time = Column(String, nullable=True)
    prorrogable_amount = Column(Float, default=0.0)
    active_prorogue = Column(Boolean, default=False)

    # Dates
    start_date = Column(Date, nullable=True)
    end_date = Column(Date, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    project = relationship("Project", back_populates="budget")
    lines = relationship("BudgetLine", back_populates="budget", cascade="all, delete-orphan")
    invoices = relationship("Invoice", back_populates="budget", cascade="all, delete-orphan")

class BudgetLine(Base):
    __tablename__ = "budget_lines"

    id = Column(Integer, primary_key=True, index=True)
    budget_id = Column(Integer, ForeignKey("project_budgets.id"), nullable=False)
    
    name = Column(String, nullable=False)
    subtotal = Column(Float, default=0.0)
    tax_percentage = Column(Float, default=13.0) # Standard 13% default

    budget = relationship("ProjectBudget", back_populates="lines")
    invoices = relationship("Invoice", back_populates="line")

    @property
    def check_tax_amount(self):
        return self.subtotal * (self.tax_percentage / 100.0)

    @property
    def total(self):
        return self.subtotal + self.check_tax_amount

class Invoice(Base):
    __tablename__ = "invoices"

    id = Column(Integer, primary_key=True, index=True)
    budget_id = Column(Integer, ForeignKey("project_budgets.id"), nullable=False)
    budget_line_id = Column(Integer, ForeignKey("budget_lines.id"), nullable=False) # Link to specific line
    
    invoice_number = Column(String, nullable=False)
    issue_date = Column(Date, nullable=False)
    due_date = Column(Date, nullable=False)
    amount = Column(Float, default=0.0)
    status = Column(Enum(InvoiceStatus), default=InvoiceStatus.PENDING)
    note = Column(String, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())

    budget = relationship("ProjectBudget", back_populates="invoices")
    line = relationship("BudgetLine", back_populates="invoices")
    payment = relationship("Payment", uselist=False, back_populates="invoice", cascade="all, delete-orphan")

class Payment(Base):
    __tablename__ = "payments"

    id = Column(Integer, primary_key=True, index=True)
    invoice_id = Column(Integer, ForeignKey("invoices.id"), unique=True, nullable=False)
    
    payment_date = Column(Date, nullable=False)
    deposit_number = Column(String, nullable=True) # Transfer/Deposit Ref
    amount = Column(Float, nullable=False)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    invoice = relationship("Invoice", back_populates="payment")
