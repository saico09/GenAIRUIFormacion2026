"""Mismas reglas y mensajes que InputRules.java: el portal muestra lo mismo con ambas APIs."""

import re
import unicodedata
from datetime import date
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, StringConstraints, field_validator, model_validator
from pydantic_core import PydanticCustomError

PATIENT_ID_MAX = 2147483647
EMPTY = "No registrado."
CLINICAL_MAX = 2000
# Todos los separadores Zs (U+00A0 incluido) están en el plano básico.
EDGE = " \t\n\r" + "".join(char for char in map(chr, range(0x10000)) if unicodedata.category(char) == "Zs")
FORBIDDEN = {"Cc", "Cf", "Zl", "Zp", "Cs"}
# Sólo LF separa líneas; un '#' dentro del texto (#hashtag) no es encabezado.
HEADING = re.compile(r"^#{1,6}(?:[ \t]|$)", re.M)
UUID_TEXT = re.compile(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}")
NAME_MESSAGE = "Usa entre 1 y 200 caracteres, sin tabuladores, saltos de línea ni caracteres de control o formato"
EMAIL_MESSAGE = ("Usa nombre@dominio.tld: una sola @, sin espacios ni IP y un dominio con letras "
                 "tras el último punto (máximo 254)")
# @Email de Hibernate Validator (el que usa Java): partes local y de dominio.
_ATOM = r"[a-zA-Z0-9!#$%&'*+/=?^_`{|}~\u0080-\uffff-]"
_QUOTED = r"(?:[a-zA-Z0-9!#$%&'*.(),<>\[\]:; @+/=?^_`{|}~\u0080-\uffff-]|\\\\|\\\")"
LOCAL_PART = re.compile(rf'(?:{_ATOM}+|"{_QUOTED}+")(?:\.(?:{_ATOM}+|"{_QUOTED}+"))*')
_LABEL = r"[a-zA-Z\u0080-\uffff0-9!#$%&'*+/=?^_`{|}~]+(?:-+[a-zA-Z\u0080-\uffff0-9!#$%&'*+/=?^_`{|}~]+)*"
DOMAIN = re.compile(rf"{_LABEL}(?:\.{_LABEL})*")


def problem(message: str) -> PydanticCustomError:
    # Sin el prefijo "Value error," de Pydantic: el portal muestra "campo: mensaje" como con Java.
    return PydanticCustomError("value_error", message)


def trim(value: str) -> str:
    return value.strip(EDGE)


def has_forbidden(text: str, allowed: str = "") -> bool:
    return any(char not in allowed and unicodedata.category(char) in FORBIDDEN for char in text)


def has_lone_surrogate(text: str) -> bool:
    return any(unicodedata.category(char) == "Cs" for char in text)


def patient_id(value: str) -> int:
    if re.fullmatch(r"[0-9]{1,10}", value) and 1 <= int(value) <= PATIENT_ID_MAX:
        return int(value)
    raise ValueError("patient_id debe ser un número entero entre 1 y 2147483647")


def record_id(value: str, field: str) -> str:
    if not UUID_TEXT.fullmatch(value):
        raise ValueError(f"{field} debe ser un UUID")
    return value.lower()


def clinical(value: str) -> str:
    if has_lone_surrogate(value):
        raise ValueError("contiene caracteres Unicode inválidos")
    text = trim(value.replace("\r\n", "\n").replace("\r", "\n"))
    if text == EMPTY:
        return ""
    if has_forbidden(text, "\n\t"):
        raise ValueError("no admite caracteres de control, de formato ni separadores Unicode")
    if len(text) > CLINICAL_MAX:
        raise ValueError("admite hasta 2000 caracteres")
    if HEADING.search(text):
        raise ValueError("ninguna línea puede empezar como encabezado Markdown (#)")
    return text


def normalize_email(value: str) -> str:
    """Valida como InputRules.EMAIL + @Email de Java."""
    local, at, domain = trim(value).rpartition("@")
    domain = domain.lower()
    text = local + at + domain
    tld = domain.rpartition(".")[2]
    if (not at or not local or "@" in local or not 1 <= len(text) <= 254 or "." not in domain or "[" in domain
            or any(char in " \t\n\x0b\x0c\r" or unicodedata.category(char) in FORBIDDEN | {"Zs"} for char in text)
            or not any(unicodedata.category(char).startswith("L") for char in tld)):
        raise ValueError(EMAIL_MESSAGE)
    # Hibernate cuenta la parte local en unidades UTF-16 y convierte el dominio con IDNA 2003.
    if (len(local.encode("utf-16-le")) // 2 > 64 or not LOCAL_PART.fullmatch(local)
            or domain.endswith(".") or not DOMAIN.fullmatch(domain) or not idna_ascii(domain)):
        raise ValueError("Email inválido")
    return text


def idna_ascii(domain: str) -> bool:
    if any(unicodedata.ucd_3_2_0.category(char) == "Cn" for char in domain):
        return False  # IDN.toASCII de Java rechaza puntos de código sin asignar en Unicode 3.2.
    try:
        return len(domain.encode("idna")) <= 255
    except UnicodeError:
        return False


def parse_birth_date(value):
    if not isinstance(value, str) or not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", value):
        raise problem("Usa una fecha real con formato YYYY-MM-DD")
    try:
        parsed = date.fromisoformat(value)
    except ValueError:
        raise problem("Usa una fecha real con formato YYYY-MM-DD") from None
    if parsed > date.today():
        raise problem("La fecha de nacimiento no puede ser posterior a hoy")
    return parsed


class PatientIn(BaseModel):
    name: str
    birth_date: Annotated[date, BeforeValidator(parse_birth_date)]
    email: str

    @field_validator("name")
    @classmethod
    def valid_name(cls, value: str) -> str:
        value = trim(value)
        if not 1 <= len(value) <= 200 or has_forbidden(value):
            raise problem(NAME_MESSAGE)
        return value

    @field_validator("email")
    @classmethod
    def valid_email(cls, value: str) -> str:
        try:
            return normalize_email(value)
        except ValueError as error:
            raise problem(str(error)) from None


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
        try:
            return clinical(value)
        except ValueError as error:
            raise problem(str(error)) from None

    @model_validator(mode="after")
    def at_least_one_field(self):
        if not any((self.disease, self.treatment, self.medication)):
            raise problem("Un registro necesita al menos un campo con información")
        return self


class DiseaseOut(DiseaseIn):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    patient_id: int


def free_text(value: str, blank: str, controls: str) -> str:
    if not trim(value):
        raise problem(blank)
    if has_lone_surrogate(value):
        raise problem("Contiene caracteres Unicode inválidos")
    if any(char not in "\n\r\t" and unicodedata.category(char) == "Cc" for char in value):
        raise problem(controls)
    return value


class ChatIn(BaseModel):
    patient_id: Annotated[int, Field(strict=True, gt=0, le=PATIENT_ID_MAX)]
    question: Annotated[str, StringConstraints(min_length=1, max_length=2000)]

    @field_validator("question")
    @classmethod
    def question_text(cls, value: str) -> str:
        # Conservamos el texto exacto para enviarlo a ambas ramas.
        return free_text(value, "Escribe una pregunta", "La consulta no admite caracteres de control")


class ClinicalProposalIn(BaseModel):
    patient_id: Annotated[int, Field(strict=True, gt=0, le=PATIENT_ID_MAX)]
    note: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=6000)]

    @field_validator("note")
    @classmethod
    def note_text(cls, value: str) -> str:
        return free_text(value, "Escribe una nota", "La nota no admite caracteres de control")
