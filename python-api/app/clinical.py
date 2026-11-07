"""Identidad clínica Java y lectura de su informe confirmado, sin escrituras clínicas."""

import hashlib
import os
from threading import RLock
from urllib.error import HTTPError

from app.history_index import index_history, remove_patient_index
from app.knowledge import request_json

JAVA_API_BASE_URL = os.getenv("JAVA_API_BASE_URL", "http://java-api:8080").rstrip("/")
_sync_lock = RLock()


class ClinicalUnavailable(OSError):
    pass


class ClinicalPatientMissing(LookupError):
    pass


def read_java(path: str) -> dict:
    try:
        return request_json("GET", JAVA_API_BASE_URL + path, timeout=10)
    except HTTPError as error:
        if error.code == 404:
            raise ClinicalPatientMissing("Paciente no encontrado en Java") from error
        raise ClinicalUnavailable("No se pudo leer la historia de Java") from error
    except (OSError, ValueError) as error:
        raise ClinicalUnavailable("Java no disponible; no se usará una historia desactualizada") from error


def get_clinical_patient(patient_id: int) -> dict:
    return read_java(f"/patients/{patient_id}")


def get_history(patient_id: int) -> dict:
    history = read_java(f"/patients/{patient_id}/history")
    try:
        valid = history["patient_id"] == patient_id and isinstance(history["entries"], list)
        valid = valid and hashlib.sha256(history["markdown"].encode("utf-8")).hexdigest() == history["revision"]
        if not valid:
            raise ValueError("Revisión o paciente inconsistentes")
    except (KeyError, TypeError, ValueError) as error:
        raise ClinicalUnavailable("El informe recibido no tiene una revisión verificable") from error
    return history


def sync_history(patient_id: int, *, allow_missing: bool = False) -> dict:
    # Evita que dos peticiones de esta instancia reindexen revisiones distintas a la vez.
    with _sync_lock:
        for _ in range(3):
            try:
                history = get_history(patient_id)
            except ClinicalPatientMissing:
                if allow_missing:
                    return remove_patient_index(patient_id)
                raise
            result = index_history(history)
            try:
                latest = get_history(patient_id)
            except ClinicalPatientMissing:
                if allow_missing:
                    return remove_patient_index(patient_id)
                raise
            if latest["revision"] == history["revision"]:
                return result
        raise ClinicalUnavailable("El informe cambió mientras se indexaba; vuelve a intentarlo")
