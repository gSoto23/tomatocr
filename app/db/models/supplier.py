"""Proveedores: the companies TOMATO buys from (plants, fertilizer, tools, transport...) and
the people to call there. Admin and supervisor use it (app/routers/suppliers.py)."""
from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship

from app.db.base_class import Base

CATEGORIES = {
    "vivero": "Vivero y plantas",
    "abonos": "Abonos y agroquímicos",
    "herramientas": "Herramientas y maquinaria",
    "mantenimiento": "Mantenimiento de equipo",
    "transporte": "Transporte",
    "materiales": "Materiales (tierra, piedra, madera)",
    "otro": "Otro",
}
PAYMENT_TERMS = ("Contado", "Crédito 15 días", "Crédito 30 días", "Crédito 60 días")


class Supplier(Base):
    __tablename__ = "suppliers"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(200), nullable=False)
    category = Column(String(20), nullable=False, default="otro", server_default="otro", index=True)
    # Cédula jurídica or física, as written on their invoices.
    tax_id = Column(String(30), nullable=True)
    iban = Column(String(40), nullable=True)
    sinpe = Column(String(30), nullable=True)
    payment_terms = Column(String(60), nullable=True)
    notes = Column(Text, nullable=True)
    created_by_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    contacts = relationship("SupplierContact", back_populates="supplier", cascade="all, delete-orphan",
                            order_by="SupplierContact.id")


class SupplierContact(Base):
    __tablename__ = "supplier_contacts"

    id = Column(Integer, primary_key=True, index=True)
    supplier_id = Column(Integer, ForeignKey("suppliers.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String(120), nullable=False)
    role = Column(String(80), nullable=True)
    phone = Column(String(30), nullable=True)
    email = Column(String(120), nullable=True)

    supplier = relationship("Supplier", back_populates="contacts")
