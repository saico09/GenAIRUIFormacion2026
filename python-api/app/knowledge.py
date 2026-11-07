"""Acceso HTTP compartido por la preparación, ingesta y búsqueda de historias."""

import json
import math
import os
import re
from urllib.request import Request, urlopen

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/")
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "nomic-embed-text")
QDRANT_URL = os.getenv("QDRANT_URL", "http://localhost:6333").rstrip("/")
COLLECTION = os.getenv("QDRANT_COLLECTION", "historias")
if not re.fullmatch(r"[A-Za-z0-9_-]{1,80}", COLLECTION):
    raise ValueError("QDRANT_COLLECTION debe ser un nombre simple de colección")
HISTORY_AUTO_SYNC = os.getenv("HISTORY_AUTO_SYNC", "true").lower() == "true"


class EmbeddingUnavailable(OSError):
    """No se pudo obtener un vector del modelo de embeddings."""


class QdrantUnavailable(OSError):
    """No se pudo consultar la base vectorial."""


def request_json(method: str, url: str, data: dict | None = None, timeout: int = 120,
                 headers: dict | None = None) -> dict:
    body = None if data is None else json.dumps(data, ensure_ascii=False).encode("utf-8")
    request = Request(url, data=body, headers={"Content-Type": "application/json", **(headers or {})}, method=method)
    with urlopen(request, timeout=timeout) as response:
        return json.load(response)


def embed(text: str, *, query: bool = False) -> list[float]:
    # Nomic distingue documentos de consultas mediante estos prefijos.
    prefix = "search_query: " if query else "search_document: "
    try:
        result = request_json("POST", f"{OLLAMA_BASE_URL}/api/embed", {
            "model": EMBEDDING_MODEL, "input": prefix + text, "truncate": False,
            "keep_alive": "1m",
        })
        vector = result["embeddings"][0]
        if not vector or not all(isinstance(n, (int, float)) and math.isfinite(n) for n in vector):
            raise ValueError("Ollama devolvió un vector vacío o inválido")
        return vector
    except (OSError, ValueError, KeyError, IndexError, TypeError) as error:
        raise EmbeddingUnavailable("Embeddings no disponibles") from error


def qdrant(method: str, path: str, data: dict | None = None) -> dict:
    try:
        return request_json(method, f"{QDRANT_URL}{path}", data)
    except (OSError, ValueError) as error:
        raise QdrantUnavailable("Qdrant no disponible") from error


def prepare_collection() -> dict:
    vector = embed("Enfermedad Alfa")
    names = {entry["name"] for entry in qdrant("GET", "/collections")["result"]["collections"]}
    if COLLECTION not in names:
        qdrant("PUT", f"/collections/{COLLECTION}", {
            "vectors": {"size": len(vector), "distance": "Cosine"},
        })
    config = qdrant("GET", f"/collections/{COLLECTION}")["result"]["config"]["params"]["vectors"]
    if config["size"] != len(vector) or config["distance"] != "Cosine":
        raise ValueError("La colección existente no coincide con el embedding; no se modificó")
    return {"model": EMBEDDING_MODEL, "collection": COLLECTION, **config}


def search_fragments(patient_id: int, question: str) -> list[dict]:
    """Devuelve hasta tres fragmentos del informe confirmado del paciente Java."""
    if patient_id < 1 or not question.strip():
        raise ValueError("Se requieren un patient_id positivo y una pregunta no vacía")
    revision = None
    if HISTORY_AUTO_SYNC:
        from app.clinical import sync_history
        revision = sync_history(patient_id)["revision"]
    conditions = [{"key": "patient_id", "match": {"value": patient_id}},
                  {"key": "registry", "match": {"value": "java"}}]
    if revision:
        conditions.append({"key": "revision", "match": {"value": revision}})
    vector = embed(question.strip(), query=True)

    def query(extra_conditions: list[dict], limit: int = 3) -> list[dict]:
        return qdrant("POST", f"/collections/{COLLECTION}/points/query", {
            "query": vector, "filter": {"must": conditions + extra_conditions},
            "limit": limit, "with_payload": True, "with_vector": False,
        })["result"]["points"]

    # Las preguntas repetidas no deben desplazar los tres hechos clínicos confirmados.
    # Para síntomas o consultas anteriores se reserva un fragmento a lo relatado por el usuario.
    from rag import asks_about_reported_history, explicitly_asks_for_consultations, is_record_lookup
    include_reported = not is_record_lookup(question) or asks_about_reported_history(question)
    confirmed = query([{"key": "section", "match": {"any": ["Enfermedad", "Tratamiento", "Medicamento"]}}])
    journal_lookup = explicitly_asks_for_consultations(question)
    reported = query([{"key": "section", "match": {"value": "Consulta"}}], 3 if journal_lookup else 1) if include_reported else []
    result = reported if journal_lookup and reported else confirmed[:2] + reported if reported else confirmed
    if len(result) < 3:
        # Sin registros confirmados, se pueden recuperar hasta tres notas del usuario.
        used = {point["id"] for point in result}
        result.extend(point for point in query([]) if point["id"] not in used)
        result = result[:3]
    fragments = []
    for point in result:
        payload = point["payload"]
        if payload["patient_id"] != patient_id:
            raise ValueError("Qdrant devolvió un fragmento de otro paciente")
        fragments.append({"score": point["score"], **{
            key: payload[key] for key in ("patient_id", "record_id", "source", "section", "text")
        }})
    return fragments
