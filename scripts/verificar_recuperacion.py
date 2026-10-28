"""Ejecutar dentro de python-api por stdin; no modifica datos."""

import json
from pathlib import Path

from app.knowledge import search_fragments
from ingestar import load_fragments, verify_fragments

documents = load_fragments(Path("/datos"))
stored = verify_fragments(documents)
assert stored["count"] == 9 and stored["per_patient"] == {1: 3, 2: 3, 3: 3}
payloads = [document["payload"] for document in documents]
questions = json.loads(Path("/datos/preguntas.json").read_text(encoding="utf-8"))
assert len(questions) == 4, "Se esperan las cuatro preguntas del dataset"
checks = []
for question in questions:
    results = search_fragments(question["patient_id"], question["question"])
    assert len(results) == 2, "Se esperaban dos fragmentos"
    for result in results:
        assert result["patient_id"] == question["patient_id"], "Resultado de otro paciente"
        payload = {key: result[key] for key in ("patient_id", "source", "section", "text")}
        assert payload in payloads, "La fuente, sección o texto no coincide con el Markdown"
    answer_present = any(question["expected"] in result["text"] for result in results)
    if question["expected"] == "No hay información suficiente":
        # El caso ausente del dataset es la cirugía; se revisa también la fuente completa.
        patient_texts = [payload["text"].casefold() for payload in payloads
                         if payload["patient_id"] == question["patient_id"]]
        assert not any("cirug" in text for text in patient_texts), "Apareció información de cirugía"
        assert not answer_present
    else:
        assert answer_present, "No se recuperó la respuesta conocida"
    checks.append({**question, "answer_present": answer_present, "results": results})
assert sum(check["answer_present"] for check in checks) == 3
print(json.dumps({"count": stored["count"], "per_patient": stored["per_patient"],
                  "payloads_match": True, "queries": checks}, ensure_ascii=False, indent=2))
