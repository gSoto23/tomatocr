from sqlalchemy import Column, Integer, String, Float, Boolean, Date, ForeignKey
from sqlalchemy.orm import relationship
from app.db.base import Base

class ProjectBudget(Base):
    __tablename__ = "project_budgets"

    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey("projects.id"), unique=True, nullable=False)
    licitation_number = Column(String(100), nullable=True)
    contract_duration = Column(String(100), nullable=True)  # "2 años", "6 meses"
    is_prorrogable = Column(Boolean, default=False)
    prorrogable_time = Column(String(100), nullable=True)
    prorrogable_amount = Column(Float, nullable=True)

    project = relationship("Project", back_populates="budget")
    lines = relationship("BudgetLine", back_populates="budget", cascade="all, delete-orphan")
    invoices = relationship("Invoice", back_populates="budget", cascade="all, delete-orphan")


class BudgetLine(Base):
    __tablename__ = "budget_lines"

    id = Column(Integer, primary_key=True, index=True)
    budget_id = Column(Integer, ForeignKey("project_budgets.id"), nullable=False)
    name = Column(String(255), nullable=False)
    subtotal = Column(Float, nullable=False)
    tax_percentage = Column(Float, default=13.0)
    
    # helper property or computed? For DB we store raw values.
    # total can be computed in Python or DB. Let's compute in Python property usually, 
    # but if valid requirement is "Total línea", we usually just calculate it on read.
    # We will stick to basic columns.

    budget = relationship("ProjectBudget", back_populates="lines")
    invoices = relationship("Invoice", back_populates="line")


class Invoice(Base):
    __tablename__ = "invoices"

    id = Column(Integer, primary_key=True, index=True)
    budget_id = Column(Integer, ForeignKey("project_budgets.id"), nullable=False)
    line_id = Column(Integer, ForeignKey("budget_lines.id"), nullable=False)
    
    date_issued = Column(Date, nullable=False)
    invoice_number = Column(String(50), nullable=False)
    amount = Column(Float, nullable=False)
    due_date = Column(Date, nullable=False)
    
    # Status: pending, overdue, paid. 
    # Can be computed, but storing "paid" explicit field is good.
    # We will store 'status' string for simplicity or compute it. 
    # Reqs say: "Estado inicial: Si hoy > due_date -> vencida, else pendiente".
    # Payment: "Pagada" is definitive.
    # So we can effectively check: if payment_date is not None -> Paid. Else check date.
    # However, user asks for "Estado" column likely.
    # Let's add a `is_paid` boolean or `status` string?
    # "Al crear... Estado inicial...".
    # I'll stick to dynamic computation for Pending/Overdue, and explicitly store Payment info.
    # But usually a cached status is helpful for filtering.
    # I'll add `status` column but maintain it carefully, OR just rely on `payment_date`.
    # Requirement 3B.3: "Estado (pendiente / vencida / pagada)". 
    # Requirement 4: "Pendiente / Vencida se calcula automáticamente... Pagada se define manualmente".
    # So I wont store "Pendiente/Vencida" persistently if it changes by time.
    # I will store `payment_date` and `deposit_number`, `paid_amount`.
    
    payment_date = Column(Date, nullable=True)
    deposit_number = Column(String(100), nullable=True)
    paid_amount = Column(Float, nullable=True)

    budget = relationship("ProjectBudget", back_populates="invoices")
    line = relationship("BudgetLine", back_populates="invoices")
