"""Sincronización idempotente por paciente; conserva colecciones y pacientes ajenos."""

from app.history_documents import fragments_from_history
from app.knowledge import COLLECTION, embed, prepare_collection, qdrant


def patient_points(patient_id: int) -> list[dict]:
    points = []
    offset = None
    while True:
        body = {"filter": {"must": [{"key": "patient_id", "match": {"value": patient_id}}]},
                "limit": 100, "with_payload": True, "with_vector": False}
        if offset is not None:
            body["offset"] = offset
        result = qdrant("POST", f"/collections/{COLLECTION}/points/scroll", body)["result"]
        # Los puntos anteriores a esta ampliación no tenían registry.
        points.extend(point for point in result["points"] if point["payload"].get("registry") in (None, "java"))
        offset = result.get("next_page_offset")
        if offset is None:
            return points


def index_history(history: dict) -> dict:
    config = prepare_collection()
    expected = fragments_from_history(history)
    previous = patient_points(history["patient_id"])
    old = {point["id"]: point["payload"] for point in previous}
    wanted = {point["id"]: point["payload"] for point in expected}
    if old != wanted:
        changed = []
        for point in expected:
            if old.get(point["id"]) != point["payload"]:
                vector = embed(f"{point['payload']['section']}: {point['payload']['text']}")
                if len(vector) != config["size"]:
                    raise ValueError("Dimensión de embedding distinta de la colección")
                changed.append({**point, "vector": vector})
        # Primero se escriben y confirman los nuevos puntos. Sólo después se quitan los obsoletos.
        if changed:
            qdrant("PUT", f"/collections/{COLLECTION}/points?wait=true", {"points": changed})
        removed = sorted(old.keys() - wanted.keys())
        if removed:
            qdrant("POST", f"/collections/{COLLECTION}/points/delete?wait=true", {"points": removed})
    stored = {point["id"]: point["payload"] for point in patient_points(history["patient_id"])}
    if stored != wanted:
        raise ValueError("El índice no coincide con la revisión confirmada del informe")
    return {"patient_id": history["patient_id"], "filename": history["filename"],
            "revision": history["revision"], "records": len(history["entries"]),
            "fragments": len(expected), "status": "synced"}


def remove_patient_index(patient_id: int) -> dict:
    names = {row["name"] for row in qdrant("GET", "/collections")["result"]["collections"]}
    if COLLECTION in names:
        identifiers = [point["id"] for point in patient_points(patient_id)]
        if identifiers:
            qdrant("POST", f"/collections/{COLLECTION}/points/delete?wait=true", {"points": identifiers})
    return {"patient_id": patient_id, "status": "removed", "records": 0, "fragments": 0}
