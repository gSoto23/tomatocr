"""CRM ("Clientes" in the UI): accounts (prospects and clients in one table), their
contacts, opportunities and follow-ups ("Seguimientos"). See docs/DISENO_CRM.md and
docs/ANALISIS_ENCAJE_CRM.md."""
from datetime import datetime

from sqlalchemy import (Column, Integer, String, Text, Boolean, Date, DateTime, Float, ForeignKey,
                        UniqueConstraint)
from sqlalchemy.orm import relationship

from app.db.base_class import Base

ACCOUNT_KINDS = ("empresa", "institucion_publica", "condominio", "hotel", "persona", "otro")
# Account status is computed from its projects (see app.utils.crm.account_status);
# only "descartada" is set by hand (discarded_at).
ACCOUNT_STATUSES = ("prospecto", "cliente", "ex_cliente", "descartada")
MOTORS = ("esg", "regalo_corporativo", "mantenimiento", "tienda", "sector_publico")
OPPORTUNITY_KINDS = ("nuevo", "renovacion", "ampliacion")
# Order matters: max_stage stores the index of the highest stage reached.
STAGES = ("prospecto", "respuesta", "reunion", "propuesta", "ganado", "perdido")
ACTIVITY_TYPES = ("llamada", "correo", "whatsapp", "visita", "reunion", "nota", "cambio_etapa")


# Stages counted in the funnel, in order ("perdido" is not a step of the funnel).
FUNNEL_STAGES = STAGES[:5]
# Only these stages have a target (editable by admin; 0 = no target). The earlier boxes show
# the share that passed from the previous box instead: there is no data yet to set real
# targets for them (decided 29/09/2026).
GOAL_STAGES = ("propuesta", "ganado")
DEFAULT_GOALS = {"prospecto": 0, "respuesta": 0, "reunion": 0, "propuesta": 10, "ganado": 4}

LABELS = {
    "stage": {"prospecto": "Nueva", "respuesta": "Respuesta", "reunion": "Reunión", "propuesta": "Propuesta",
              "ganado": "Ganado", "perdido": "Perdido"},
    "motor": {"esg": "ESG", "regalo_corporativo": "Regalo corporativo", "mantenimiento": "Mantenimiento",
              "tienda": "Tienda", "sector_publico": "Sector público"},
    "kind": {"empresa": "Empresa", "institucion_publica": "Institución pública", "condominio": "Condominio",
             "hotel": "Hotel", "persona": "Persona", "otro": "Otro"},
    "status": {"prospecto": "Oportunidad", "cliente": "Cliente", "ex_cliente": "Ex-cliente", "descartada": "Descartada"},
    "activity": {"llamada": "Llamada", "correo": "Correo", "whatsapp": "WhatsApp", "visita": "Visita",
                 "reunion": "Reunión", "nota": "Nota", "cambio_etapa": "Cambio de etapa"},
    "opportunity_kind": {"nuevo": "Nuevo", "renovacion": "Renovación", "ampliacion": "Ampliación"},
}


def stage_index(stage: str) -> int:
    return STAGES.index(stage)


class Account(Base):
    __tablename__ = "accounts"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(200), nullable=False, index=True)
    legal_name = Column(String(200), nullable=True)
    # Cédula física o jurídica. Unique when present (NULLs don't collide).
    tax_id = Column(String(30), nullable=True, unique=True)
    kind = Column(String(30), nullable=False, default="otro", server_default="otro")
    # Set by hand when an account won't move forward; the other statuses are computed.
    # Discarded accounts leave the tables and go to the "Descartados" list.
    discarded_at = Column(DateTime, nullable=True)
    discard_reason = Column(Text, nullable=True)
    source = Column(String(30), nullable=True)
    owner_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    province = Column(String(50), nullable=True)
    address = Column(Text, nullable=True)
    website = Column(String(200), nullable=True)
    vat_exemption_code = Column(String(50), nullable=True)
    notes = Column(Text, nullable=True)
    # Where the record first came from (e.g. "user:12", "project:5", "quote:33").
    origin_ref = Column(String(50), nullable=True)
    merged_into_id = Column(Integer, ForeignKey("accounts.id"), nullable=True)
    created_by_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    owner = relationship("User", foreign_keys=[owner_id])
    contacts = relationship("Contact", back_populates="account", order_by="Contact.id")
    opportunities = relationship("Opportunity", back_populates="account", order_by="Opportunity.id")
    activities = relationship("CrmActivity", back_populates="account", order_by="CrmActivity.happened_at")
    merged_into = relationship("Account", remote_side=[id])


class Contact(Base):
    __tablename__ = "contacts"

    id = Column(Integer, primary_key=True, index=True)
    account_id = Column(Integer, ForeignKey("accounts.id"), nullable=False, index=True)
    name = Column(String(150), nullable=False)
    role_title = Column(String(100), nullable=True)
    email = Column(String(150), nullable=True, index=True)
    phone = Column(String(30), nullable=True)
    is_primary = Column(Boolean, nullable=False, default=False, server_default="false")
    # What the contact is for, account-wide. Site contacts and report recipients are
    # set per project in ProjectContactRole.
    is_commercial = Column(Boolean, nullable=False, default=False, server_default="false")
    is_billing = Column(Boolean, nullable=False, default=False, server_default="false")
    # Portal user when the person has access (role client).
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True, unique=True)
    consent_marketing = Column(Boolean, nullable=False, default=False, server_default="false")
    consent_at = Column(DateTime, nullable=True)
    consent_text_version = Column(String(20), nullable=True)
    notes = Column(Text, nullable=True)
    origin_ref = Column(String(50), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    account = relationship("Account", back_populates="contacts")
    user = relationship("User")


class Opportunity(Base):
    __tablename__ = "opportunities"

    id = Column(Integer, primary_key=True, index=True)
    account_id = Column(Integer, ForeignKey("accounts.id"), nullable=False, index=True)
    title = Column(String(200), nullable=False)
    kind = Column(String(20), nullable=False, default="nuevo", server_default="nuevo")
    motor = Column(String(30), nullable=True)
    stage = Column(String(20), nullable=False, default="prospecto", server_default="prospecto")
    max_stage = Column(Integer, nullable=False, default=0, server_default="0")
    lost_reason = Column(Text, nullable=True)
    amount_crc = Column(Float, nullable=True)
    expected_close_date = Column(Date, nullable=True)
    owner_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    next_step = Column(String(255), nullable=True)
    next_step_date = Column(Date, nullable=True)
    source = Column(String(30), nullable=True)
    # Where it came from, for idempotent imports (e.g. "tablero:<id>").
    origin_ref = Column(String(80), nullable=True, index=True)
    # projects.opportunity_id points back here; use_alter breaks the cycle for create/drop order.
    project_id = Column(Integer, ForeignKey("projects.id", use_alter=True, name="fk_opportunities_project_id"),
                        nullable=True)
    created_by_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    account = relationship("Account", back_populates="opportunities")
    owner = relationship("User", foreign_keys=[owner_id])


class CrmActivity(Base):
    __tablename__ = "crm_activities"

    id = Column(Integer, primary_key=True, index=True)
    account_id = Column(Integer, ForeignKey("accounts.id"), nullable=False, index=True)
    opportunity_id = Column(Integer, ForeignKey("opportunities.id"), nullable=True)
    contact_id = Column(Integer, ForeignKey("contacts.id"), nullable=True)
    type = Column(String(20), nullable=False)
    happened_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    notes = Column(Text, nullable=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    account = relationship("Account", back_populates="activities")
    user = relationship("User")


class AccountNotDuplicate(Base):
    """Pairs an admin reviewed and marked as different accounts (lower id first)."""
    __tablename__ = "account_not_duplicates"
    __table_args__ = (UniqueConstraint("account_a_id", "account_b_id", name="uq_account_not_duplicates_pair"),)

    id = Column(Integer, primary_key=True)
    account_a_id = Column(Integer, ForeignKey("accounts.id"), nullable=False)
    account_b_id = Column(Integer, ForeignKey("accounts.id"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class ProjectContactRole(Base):
    """Which of the account's contacts a project uses: on site and/or receiving the
    daily-log reports. One contact list per account; projects pick from it."""
    __tablename__ = "project_contact_roles"

    project_id = Column(Integer, ForeignKey("projects.id"), primary_key=True)
    contact_id = Column(Integer, ForeignKey("contacts.id"), primary_key=True)
    is_site = Column(Boolean, nullable=False, default=True, server_default="true")
    receives_reports = Column(Boolean, nullable=False, default=False, server_default="false")
    position = Column(String(100), nullable=True)  # role on this site, e.g. "Encargado de obra"

    contact = relationship("Contact")


class CrmGoal(Base):
    """Funnel target per stage (accounts that should reach it)."""
    __tablename__ = "crm_goals"

    stage = Column(String(20), primary_key=True)
    target = Column(Integer, nullable=False)


class CrmSetting(Base):
    """Small CRM settings editable by admin, e.g. the funnel period (funnel_start, funnel_end)."""
    __tablename__ = "crm_settings"

    key = Column(String(50), primary_key=True)
    value = Column(String(200), nullable=True)


# Who gets new web and darboles.com leads, per motor. "_default" is the fallback.
ASSIGNMENT_DEFAULT = "_default"


class CrmAssignment(Base):
    __tablename__ = "crm_assignments"

    motor = Column(String(30), primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)

    user = relationship("User")


class LeadSubmission(Base):
    """One accepted or rejected lead submission, for rate limiting (web form and API)."""
    __tablename__ = "lead_submissions"

    id = Column(Integer, primary_key=True)
    source = Column(String(20), nullable=False)
    ip_address = Column(String(50), nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)
