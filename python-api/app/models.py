from datetime import date, datetime
from uuid import UUID

from sqlalchemy import (
    Boolean, CheckConstraint, Date, DateTime, Double, Identity, Index, String, Text, Uuid, text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class Patient(Base):
    # Tabla public.patients en PostgreSQL
    __tablename__ = "patients"

    id: Mapped[int] = mapped_column(Identity(), primary_key=True)  # autogenerado por PostgreSQL
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    birth_date: Mapped[date] = mapped_column(Date, nullable=False)
    email: Mapped[str] = mapped_column(String(320), nullable=False)


class TransactionLog(Base):
    """Una fila por petición API; execution_id permite unir Python y Java."""

    __tablename__ = "transaction_logs"
    __table_args__ = (
        CheckConstraint("service IN ('python', 'java')", name="transaction_logs_service_check"),
        Index("transaction_logs_execution_id", "execution_id"),
        {"schema": "public"},
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    execution_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    request_id: Mapped[str] = mapped_column(Text, nullable=False)
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
