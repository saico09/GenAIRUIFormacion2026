from datetime import date

from sqlalchemy import Date, Identity, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class Patient(Base):
    # Tabla public.patients en PostgreSQL
    __tablename__ = "patients"

    id: Mapped[int] = mapped_column(Identity(), primary_key=True)  # autogenerado por PostgreSQL
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    birth_date: Mapped[date] = mapped_column(Date, nullable=False)
    email: Mapped[str] = mapped_column(String(320), nullable=False)
