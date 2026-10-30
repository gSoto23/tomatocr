"""Posibles clientes: the sellers' prospecting list, before the Filtro. A company someone
plans to call is not an opportunity yet; it becomes one ("Convertir en oportunidad") when there
is real contact, so the Filtro and the goals only count real work. Every seller sees the whole
list (so two don't call the same company); its seller and the admin change it."""
from datetime import datetime

from sqlalchemy import Column, Date, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship

from app.db.base_class import Base

STATUSES = {"por_contactar": "Por contactar", "en_seguimiento": "En seguimiento",
            "convertido": "Convertido", "descartado": "No le interesa"}
OPEN_STATUSES = ("por_contactar", "en_seguimiento")
SOURCES = {"directorio": "Directorio o lista", "referido": "Referido", "visita": "Visita en la zona",
           "redes": "Redes sociales", "sicop": "SICOP", "otro": "Otro"}
CHANNELS = {"llamada": "Llamada", "whatsapp": "WhatsApp", "correo": "Correo", "visita": "Visita", "otro": "Otro"}
PROVINCES = ("San José", "Alajuela", "Cartago", "Heredia", "Guanacaste", "Puntarenas", "Limón")


class Prospect(Base):
    __tablename__ = "prospects"

    id = Column(Integer, primary_key=True, index=True)
    company = Column(String(200), nullable=False)
    contact_name = Column(String(150), nullable=True)
    contact_role = Column(String(100), nullable=True)
    phone = Column(String(30), nullable=True)
    email = Column(String(150), nullable=True)
    kind = Column(String(30), nullable=False, default="empresa", server_default="empresa")
    motor = Column(String(30), nullable=True)
    province = Column(String(50), nullable=True)
    source = Column(String(20), nullable=True)
    notes = Column(Text, nullable=True)
    owner_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    status = Column(String(20), nullable=False, default="por_contactar", server_default="por_contactar", index=True)
    next_contact_date = Column(Date, nullable=True, index=True)
    last_contact_at = Column(DateTime, nullable=True)
    discard_reason = Column(Text, nullable=True)
    # Once converted: the account (new or existing) and the opportunity it got.
    account_id = Column(Integer, ForeignKey("accounts.id"), nullable=True)
    opportunity_id = Column(Integer, ForeignKey("opportunities.id"), nullable=True)
    converted_at = Column(DateTime, nullable=True)
    created_by_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    owner = relationship("User", foreign_keys=[owner_id])
    attempts = relationship("ProspectAttempt", back_populates="prospect", cascade="all, delete-orphan",
                            order_by="ProspectAttempt.happened_at.desc()")

    @property
    def is_open(self) -> bool:
        return self.status in OPEN_STATUSES


class ProspectAttempt(Base):
    """One try to reach the prospect: a call, a WhatsApp, a visit, with what happened."""
    __tablename__ = "prospect_attempts"

    id = Column(Integer, primary_key=True, index=True)
    prospect_id = Column(Integer, ForeignKey("prospects.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    channel = Column(String(20), nullable=False, default="llamada", server_default="llamada")
    notes = Column(Text, nullable=True)
    happened_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    prospect = relationship("Prospect", back_populates="attempts")
    user = relationship("User")
