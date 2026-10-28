import re
from datetime import date
from typing import Annotated

from pydantic import BaseModel, BeforeValidator, ConfigDict, EmailStr, Field, StringConstraints, field_validator

# Si algún campo no cumple, FastAPI responde 422 sin llegar a la base de datos.


def solo_yyyy_mm_dd(value):
    # Corre antes de convertir a date: solo deja pasar texto con forma YYYY-MM-DD (rechaza 10-01-1990 o números)
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        raise ValueError("birth_date debe ser texto con formato YYYY-MM-DD")
    return value


class PatientIn(BaseModel):
    # name: se quitan espacios de los bordes y no puede quedar vacío
    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
    # birth_date: primero el formato y después Pydantic comprueba que la fecha exista (rechaza 2026-02-30)
    birth_date: Annotated[date, BeforeValidator(solo_yyyy_mm_dd)]
    # email: lo valida la librería email-validator
    email: EmailStr


class PatientOut(BaseModel):
    # from_attributes permite construir la respuesta directo desde el objeto de SQLAlchemy
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    birth_date: date
    email: str


class ChatIn(BaseModel):
    patient_id: Annotated[int, Field(strict=True, gt=0)]
    question: Annotated[str, StringConstraints(min_length=1, max_length=2000)]

    @field_validator("question")
    @classmethod
    def question_not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Escribe una pregunta")
        # Conservamos el texto exacto para enviarlo a ambas ramas.
        return value
