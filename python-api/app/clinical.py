"""Java conserva los informes; las consultas se registran aparte de los diagnósticos."""

import hashlib
import os
from threading import RLock
from urllib.error import HTTPError

from app.history_index import index_history, remove_patient_index
from app.knowledge import request_json
from app.observability import execution_id_context, request_id_context

JAVA_API_BASE_URL = os.getenv("JAVA_API_BASE_URL", "http://java-api:8080").rstrip("/")
_sync_lock = RLock()


class ClinicalUnavailable(OSError):
    pass


class ClinicalPatientMissing(LookupError):
    pass


class ConsultationConflict(ValueError):
    pass


def correlation_headers() -> dict:
    return {key: value for key, value in {
        "X-Execution-ID": execution_id_context.get(), "X-Request-ID": request_id_context.get()
    }.items() if value}


def read_java(path: str) -> dict:
    try:
        return request_json("GET", JAVA_API_BASE_URL + path, timeout=10, headers=correlation_headers())
    except HTTPError as error:
        if error.code == 404:
            raise ClinicalPatientMissing("Paciente no encontrado en Java") from error
        raise ClinicalUnavailable("No se pudo leer la historia de Java") from error
    except (OSError, ValueError) as error:
        raise ClinicalUnavailable("Java no disponible; no se usará una historia desactualizada") from error


def get_clinical_patient(patient_id: int) -> dict:
    return read_java(f"/patients/{patient_id}")


def get_consultation(patient_id: int, execution_id: str, question: str) -> dict | None:
    try:
        result = read_java(f"/patients/{patient_id}/consultations/{execution_id}")
    except ClinicalPatientMissing:
        return None
    if result["question"] != question:
        raise ConsultationConflict("Este UUID ya corresponde a otra consulta; inicia una nueva ejecución")
    return result


def save_consultation(patient_id: int, execution_id: str, question: str, result: dict, model: str) -> dict:
    payload = {"id": execution_id, "question": question, "direct_answer": result["direct_answer"],
               "rag_answer": result["rag_answer"], "sources": result["sources"], "model": model}
    try:
        history = request_json("POST", f"{JAVA_API_BASE_URL}/patients/{patient_id}/consultations",
                               payload, timeout=30, headers=correlation_headers())
        return next(item for item in history["consultations"] if item["id"] == execution_id)
    except HTTPError as error:
        if error.code == 409:
            existing = get_consultation(patient_id, execution_id, question)
            if existing is not None:
                return existing
            raise ConsultationConflict("El UUID pertenece a otra consulta; no se sobrescribió") from error
        raise ClinicalUnavailable("No se pudo guardar la consulta en Java y PostgreSQL; reintenta con el mismo UUID") from error
    except (OSError, ValueError, KeyError, StopIteration) as error:
        # Si se perdió la respuesta después del commit, la repetición recupera el mismo UUID.
        raise ClinicalUnavailable("No se pudo confirmar el guardado; reintenta la misma consulta para evitar duplicados") from error


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
