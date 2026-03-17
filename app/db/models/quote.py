from sqlalchemy import Column, Integer, String, Text, Float, JSON, Date, DateTime
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
    
    items = Column(JSON, nullable=True) # Array of objects
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
