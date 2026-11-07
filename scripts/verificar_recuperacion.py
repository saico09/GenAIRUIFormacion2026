"""Verifica el corpus inicial Java; no cambia SQL/Markdown, la búsqueda sincroniza su índice."""

import json
from pathlib import Path

from app.knowledge import COLLECTION, qdrant, search_fragments
from app.history_documents import fragments_from_history, load_histories
from app.history_index import patient_points
from rag import source_label

histories = load_histories(Path("/datos/historias"))
documents = [fragment for history in histories for fragment in fragments_from_history(history)]
assert len(histories) == 3 and all(len(history["entries"]) == 1 for history in histories)
stored = {"count": qdrant("POST", f"/collections/{COLLECTION}/points/count", {"exact": True})["result"]["count"], "per_patient": {}}
for history in histories:
    points = patient_points(history["patient_id"])
    expected = {point["id"]: point["payload"] for point in fragments_from_history(history)}
    assert {point["id"]: point["payload"] for point in points} == expected, "El índice no conserva registry/revision/UUID/texto del Markdown"
    stored["per_patient"][history["patient_id"]] = len(points)
assert stored["count"] == 9 and stored["per_patient"] == {1: 3, 2: 3, 3: 3}
payloads = [document["payload"] for document in documents]
questions = json.loads(Path("/datos/preguntas.json").read_text(encoding="utf-8"))
assert len(questions) == 4, "Se esperan las cuatro preguntas del dataset"
checks = []
for question in questions:
    results = search_fragments(question["patient_id"], question["question"])
    assert len(results) == 3, "Se esperaban los tres fragmentos del único registro inicial"
    for result in results:
        assert result["patient_id"] == question["patient_id"], "Resultado de otro paciente"
        keys = ("patient_id", "record_id", "source", "section", "text")
        payload = {key: result[key] for key in keys}
        assert payload in [{key: stored_payload[key] for key in keys} for stored_payload in payloads], "La fuente, UUID, sección o texto no coincide con el Markdown"
    answer_present = any(question["expected"] in result["text"] for result in results)
    if question["expected"] == "No hay información suficiente":
        # El caso ausente del dataset es la cirugía; se revisa también la fuente completa.
        patient_texts = [payload["text"].casefold() for payload in payloads
                         if payload["patient_id"] == question["patient_id"]]
        assert not any("cirug" in text for text in patient_texts), "Apareció información de cirugía"
        assert not answer_present
    else:
        assert answer_present, "No se recuperó la respuesta conocida"
    checks.append({**question, "answer_present": answer_present, "results": results,
                   "source_labels": [source_label(source) for source in results]})
assert sum(check["answer_present"] for check in checks) == 3
print(json.dumps({"count": stored["count"], "per_patient": stored["per_patient"],
                  "payloads_match": True, "queries": checks}, ensure_ascii=False, indent=2))
