"""Verifica en Qdrant los registros confirmados de los pacientes demo 1-3 y su búsqueda."""

import json
from pathlib import Path

from app.knowledge import COLLECTION, qdrant, search_fragments
from app.history_documents import fragments_from_history, parse_history
from app.history_index import patient_points
from rag import source_label

questions = json.loads(Path("/datos/preguntas.json").read_text(encoding="utf-8"))
assert len(questions) == 4, "Se esperan las cuatro preguntas del dataset"
demos = sorted({question["patient_id"] for question in questions})
assert demos == [1, 2, 3], "Las preguntas son de Ana, Bruno y Carla"
payloads = {}
stored = {"count": qdrant("POST", f"/collections/{COLLECTION}/points/count", {"exact": True})["result"]["count"], "per_patient": {}}
for patient_id in demos:
    path = next(Path("/datos/historias").glob(f"paciente-{patient_id}-*.md"))
    with path.open(encoding="utf-8", newline="") as stream:
        fragments = fragments_from_history(parse_history(stream.read(), path.name))
    payloads[patient_id] = [fragment["payload"] for fragment in fragments]
    confirmed = {fragment["id"]: fragment["payload"] for fragment in fragments if fragment["payload"]["kind"] == "confirmed_record"}
    assert confirmed, f"El paciente {patient_id} no tiene registros confirmados"
    points = {point["id"]: point["payload"] for point in patient_points(patient_id)}
    assert {key: points.get(key) for key in confirmed} == confirmed, "El índice no conserva registry/revision/UUID/texto del Markdown"
    stored["per_patient"][patient_id] = {"confirmed_fragments": len(confirmed), "points": len(points)}
checks = []
keys = ("patient_id", "record_id", "source", "section", "text")
for question in questions:
    results = search_fragments(question["patient_id"], question["question"])
    assert len(results) == 3, "Se esperaban tres fragmentos"
    known = [{key: payload[key] for key in keys} for payload in payloads[question["patient_id"]]]
    for result in results:
        assert result["patient_id"] == question["patient_id"], "Resultado de otro paciente"
        assert {key: result[key] for key in keys} in known, "La fuente, UUID, sección o texto no coincide con el Markdown"
    answer_present = any(question["expected"] in result["text"] for result in results)
    if question["expected"] == "No hay información suficiente":
        # El caso ausente del dataset es la cirugía.
        confirmed_texts = [payload["text"].casefold() for payload in payloads[question["patient_id"]]
                           if payload["kind"] == "confirmed_record"]
        assert not any("cirug" in text for text in confirmed_texts), "Apareció información de cirugía"
        assert not answer_present
    else:
        assert answer_present, "No se recuperó la respuesta conocida"
    checks.append({**question, "answer_present": answer_present, "results": results,
                   "source_labels": [source_label(source) for source in results]})
assert sum(check["answer_present"] for check in checks) == 3
print(json.dumps({"count": stored["count"], "per_patient": stored["per_patient"],
                  "confirmed_payloads_match": True, "queries": checks}, ensure_ascii=False, indent=2))
