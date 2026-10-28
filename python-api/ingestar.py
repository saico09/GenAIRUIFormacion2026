"""Carga las secciones de los Markdown sin duplicarlas al repetir la ingesta."""

import argparse
from collections import Counter
import json
from pathlib import Path
import re
from urllib.error import URLError
from uuid import NAMESPACE_URL, uuid5

from app.knowledge import COLLECTION, embed, prepare_collection, qdrant

SECTIONS = {"Enfermedad", "Tratamiento", "Medicamento"}


def load_fragments(data_dir: Path) -> list[dict]:
    fragments = []
    patient_ids = set()
    paths = sorted(data_dir.glob("paciente-*.md"))
    if not paths:
        raise ValueError(f"No hay archivos paciente-*.md en {data_dir}")
    for path in paths:
        parts = re.split(r"^##[ \t]+(.+?)[ \t]*$", path.read_text(encoding="utf-8"), flags=re.M)
        identifiers = re.findall(r"^patient_id: ([1-9][0-9]*)$", parts[0], flags=re.M)
        if len(identifiers) != 1:
            raise ValueError(f"{path.name}: falta un único patient_id entero positivo")
        patient_id = int(identifiers[0])
        if patient_id in patient_ids:
            raise ValueError(f"{path.name}: patient_id repetido en los documentos")
        patient_ids.add(patient_id)
        sections = parts[1::2]
        if len(sections) != 3 or set(sections) != SECTIONS:
            raise ValueError(f"{path.name}: se requieren Enfermedad, Tratamiento y Medicamento una vez")
        for section, body in zip(sections, parts[2::2], strict=True):
            text = body.strip()
            if not text:
                raise ValueError(f"{path.name}: sección {section} vacía")
            fragments.append({
                "id": str(uuid5(NAMESPACE_URL, f"genai:historias:{patient_id}:{section}")),
                "payload": {"patient_id": patient_id, "source": path.name, "section": section, "text": text},
            })
    return fragments


def verify_fragments(fragments: list[dict]) -> dict:
    count = qdrant("POST", f"/collections/{COLLECTION}/points/count", {"exact": True})["result"]["count"]
    result = qdrant("POST", f"/collections/{COLLECTION}/points/scroll", {
        "limit": len(fragments) + 1, "with_payload": True, "with_vector": False,
    })["result"]
    expected = {fragment["id"]: fragment["payload"] for fragment in fragments}
    stored = {point["id"]: point["payload"] for point in result["points"]}
    if count != len(fragments) or result["next_page_offset"] is not None or stored != expected:
        raise ValueError("Los puntos guardados no coinciden con los documentos; no se borraron puntos")
    return {
        "collection": COLLECTION, "count": count,
        "per_patient": dict(sorted(Counter(payload["patient_id"] for payload in stored.values()).items())),
        "payloads_match": True,
        "example": fragments[0],
    }


def ingest(data_dir: Path) -> dict:
    # Validamos todos los documentos y vectores antes de escribir en Qdrant.
    fragments = load_fragments(data_dir)
    config = prepare_collection()
    points = []
    for fragment in fragments:
        vector = embed(fragment["payload"]["text"])
        if len(vector) != config["size"]:
            raise ValueError("El embedding no coincide con la dimensión de la colección")
        points.append({**fragment, "vector": vector})
    qdrant("PUT", f"/collections/{COLLECTION}/points?wait=true", {"points": points})
    return verify_fragments(fragments)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=Path("/datos"))
    args = parser.parse_args()
    try:
        print(json.dumps(ingest(args.data_dir), ensure_ascii=False, indent=2))
    except (OSError, ValueError, URLError) as error:
        parser.exit(1, f"No se pudo completar la ingesta: {error}\n")
