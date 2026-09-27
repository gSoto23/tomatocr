from sqlalchemy import Column, Integer, String, Text, Float, JSON, Date, DateTime, ForeignKey
from sqlalchemy.sql import func
from app.db.base_class import Base

class Quote(Base):
    __tablename__ = "quotes"

    id = Column(Integer, primary_key=True, index=True)
    numero_cotizacion = Column(String(50), unique=True, index=True, nullable=False)
    fecha_emision = Column(Date, nullable=False)
    cliente_nombre = Column(String(200), nullable=False)
    cliente_datos = Column(JSON, nullable=True) # {name, id, email, phone, address}
    moneda = Column(String(10), default="CRC")
    tipo_servicio = Column(String(100))
    frecuencia = Column(String(50))
    validez_dias = Column(Integer, default=15)
    
    notes = Column(Text, nullable=True)
    terminos = Column(Text, nullable=True)
    
    subtotal = Column(Float, default=0.0)
    iva = Column(Float, default=0.0)
    total = Column(Float, default=0.0)
    # Saved so a reopened or reprinted quote keeps the same total.
    discount = Column(Float, nullable=False, default=0.0, server_default="0")
    tax_rate = Column(Float, nullable=False, default=13.0, server_default="13")
    
    items = Column(JSON, nullable=True) # Array of objects
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # CRM (docs/DISENO_CRM.md). cliente_nombre stays as the text shown today.
    account_id = Column(Integer, ForeignKey("accounts.id"), nullable=True, index=True)
    opportunity_id = Column(Integer, ForeignKey("opportunities.id"), nullable=True)
