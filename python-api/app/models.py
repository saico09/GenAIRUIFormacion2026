from datetime import date, datetime
from uuid import UUID

from sqlalchemy import (
    BigInteger, Boolean, CheckConstraint, Date, DateTime, Double, ForeignKey, Identity, Index, String, Text, Uuid, text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class Patient(Base):
    # Tabla public.patients en PostgreSQL
    __tablename__ = "patients"
    __table_args__ = {"schema": "public"}

    id: Mapped[int] = mapped_column(Identity(), primary_key=True)  # autogenerado por PostgreSQL
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    birth_date: Mapped[date] = mapped_column(Date, nullable=False)
    email: Mapped[str] = mapped_column(String(320), nullable=False)


class PatientDisease(Base):
    """Un UUID asocia los tres campos del registro Markdown con su paciente."""

    __tablename__ = "patient_diseases"
    __table_args__ = (
        CheckConstraint("btrim(disease) <> '' OR btrim(treatment) <> '' OR btrim(medication) <> ''",
                        name="patient_diseases_nonempty"),
        Index("patient_diseases_patient_id", "patient_id"),
        {"schema": "public"},
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    patient_id: Mapped[int] = mapped_column(ForeignKey("public.patients.id", ondelete="CASCADE"), nullable=False)
    disease: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    treatment: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    medication: Mapped[str] = mapped_column(Text, nullable=False, server_default="")


class MedicalConsultation(Base):
    """Diario y respaldo completo compartidos; sobreviven al borrado del paciente."""

    __tablename__ = "medical_consultations"
    __table_args__ = {"schema": "public"}
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    execution_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    patient_id: Mapped[int] = mapped_column(nullable=False)
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    question: Mapped[str | None] = mapped_column(Text)
    direct_answer: Mapped[str | None] = mapped_column(Text)
    rag_answer: Mapped[str | None] = mapped_column(Text)
    model: Mapped[str | None] = mapped_column(Text)
    sources: Mapped[list] = mapped_column(JSONB, nullable=False, server_default=text("'[]'::jsonb"))
    filename: Mapped[str] = mapped_column(Text, nullable=False)
    markdown_content: Mapped[str] = mapped_column(Text, nullable=False)
    revision: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    storage_order: Mapped[int] = mapped_column(BigInteger, Identity(always=True), nullable=False)


class TransactionLog(Base):
    """Una fila y un UUID por operación HTTP; patient_id conserva el vínculo histórico."""

    __tablename__ = "transaction_logs"
    __table_args__ = (
        CheckConstraint("service IN ('python', 'java')", name="transaction_logs_service_check"),
        Index("transaction_logs_patient_id", "patient_id"),
        {"schema": "public"},
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    patient_id: Mapped[int | None] = mapped_column(nullable=True)
    service: Mapped[str] = mapped_column(Text, nullable=False)
    operation: Mapped[str] = mapped_column(Text, nullable=False)
    method: Mapped[str] = mapped_column(Text, nullable=False)
    path: Mapped[str] = mapped_column(Text, nullable=False)
    http_status: Mapped[int] = mapped_column(nullable=False)
    request_body: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    response_body: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    duration_ms: Mapped[float] = mapped_column(Double, nullable=False)
    request_truncated: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    response_truncated: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
