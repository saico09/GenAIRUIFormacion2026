import re
from datetime import date
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, BeforeValidator, ConfigDict, EmailStr, Field, StringConstraints, field_validator, model_validator

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

    @field_validator("name")
    @classmethod
    def name_without_controls(cls, value: str) -> str:
        if any(ord(char) < 32 or 127 <= ord(char) <= 159 for char in value):
            raise ValueError("El nombre no admite caracteres de control")
        return value


class PatientOut(BaseModel):
    # from_attributes permite construir la respuesta directo desde el objeto de SQLAlchemy
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    birth_date: date
    email: str


class DiseaseIn(BaseModel):
    disease: str
    treatment: str
    medication: str

    @field_validator("disease", "treatment", "medication")
    @classmethod
    def clinical_text(cls, value: str) -> str:
        value = value.replace("\r\n", "\n").strip()
        if (len(value.encode("utf-16-le")) // 2 > 2000
                or re.search(r"^#{1,6}(?:\s|$)", value, re.M)
                or any((ord(char) < 32 or 127 <= ord(char) <= 159) and char not in "\n\t" for char in value)):
            raise ValueError("Cada campo admite hasta 2000 caracteres, sin encabezados ni controles")
        return "" if value == "No registrado." else value

    @model_validator(mode="after")
    def at_least_one_field(self):
        if not any((self.disease, self.treatment, self.medication)):
            raise ValueError("Un registro necesita al menos un campo con información")
        return self


class DiseaseOut(DiseaseIn):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    patient_id: int


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


class ClinicalProposalIn(BaseModel):
    patient_id: Annotated[int, Field(strict=True, gt=0)]
    note: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=6000)]
