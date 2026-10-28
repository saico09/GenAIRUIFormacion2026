"""Acceso HTTP compartido por la preparación, ingesta y búsqueda de historias."""

import json
import math
import os
from urllib.request import Request, urlopen

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/")
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "nomic-embed-text")
QDRANT_URL = os.getenv("QDRANT_URL", "http://localhost:6333").rstrip("/")
COLLECTION = "historias"


def request_json(method: str, url: str, data: dict | None = None, timeout: int = 120) -> dict:
    body = None if data is None else json.dumps(data, ensure_ascii=False).encode("utf-8")
    request = Request(url, data=body, headers={"Content-Type": "application/json"}, method=method)
    with urlopen(request, timeout=timeout) as response:
        return json.load(response)


def embed(text: str, *, query: bool = False) -> list[float]:
    # Nomic distingue documentos de consultas mediante estos prefijos.
    prefix = "search_query: " if query else "search_document: "
    result = request_json("POST", f"{OLLAMA_BASE_URL}/api/embed", {
        "model": EMBEDDING_MODEL, "input": prefix + text, "truncate": False,
        "keep_alive": "1m",
    })
    vector = result["embeddings"][0]
    if not vector or not all(isinstance(n, (int, float)) and math.isfinite(n) for n in vector):
        raise ValueError("Ollama devolvió un vector vacío o inválido")
    return vector


def qdrant(method: str, path: str, data: dict | None = None) -> dict:
    return request_json(method, f"{QDRANT_URL}{path}", data)


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
    """Devuelve como máximo dos fragmentos del paciente, sin generar respuestas."""
    if patient_id < 1 or not question.strip():
        raise ValueError("Se requieren un patient_id positivo y una pregunta no vacía")
    result = qdrant("POST", f"/collections/{COLLECTION}/points/query", {
        "query": embed(question.strip(), query=True),
        "filter": {"must": [{"key": "patient_id", "match": {"value": patient_id}}]},
        "limit": 2,
        "with_payload": True,
        "with_vector": False,
    })["result"]["points"]
    fragments = []
    for point in result:
        payload = point["payload"]
        if payload["patient_id"] != patient_id:
            raise ValueError("Qdrant devolvió un fragmento de otro paciente")
        fragments.append({"score": point["score"], **{
            key: payload[key] for key in ("patient_id", "source", "section", "text")
        }})
    return fragments
