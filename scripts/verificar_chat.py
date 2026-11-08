"""Prueba la comparación real con Ollama; ejecutar en python-api por stdin."""

import json
from pathlib import Path

from app.knowledge import request_json
from app.llm import CHAT_MODEL, MODEL_OPTIONS, TIMEOUT_SECONDS
from app.history_documents import fragments_from_history, load_histories
from rag import build_rag_prompt, source_label

questions = json.loads(Path("/datos/preguntas.json").read_text(encoding="utf-8"))
cases = []
for question in (questions[0], questions[3]):
    histories = load_histories(Path("/datos/historias"))
    payloads = [fragment["payload"] for history in histories for fragment in fragments_from_history(history)]
    body = {key: question[key] for key in ("patient_id", "question")}
    response = request_json("POST", "http://localhost:8000/chat", body, timeout=360)
    cases.append({
        "request": body,
        "direct_prompt": body["question"],
        "rag_prompt": build_rag_prompt(body["question"], response["sources"]),
        "response": response,
        "known_payloads": payloads,
    })
print(json.dumps({
    "model": CHAT_MODEL, **MODEL_OPTIONS, "timeout_seconds_per_llm_call": TIMEOUT_SECONDS,
    "cases": cases,
}, ensure_ascii=False, indent=2))

for case in cases:
    response = case["response"]
    payloads = case["known_payloads"]
    assert isinstance(response["direct_answer"], str) and response["direct_answer"].strip()
    assert len(response["sources"]) == 3
    assert all(source["patient_id"] == case["request"]["patient_id"] for source in response["sources"])
    keys = ("patient_id", "record_id", "source", "section", "text")
    assert all({key: source[key] for key in keys} in [{key: value[key] for key in keys} for value in payloads]
               for source in response["sources"])
    assert case["direct_prompt"] == case["request"]["question"]
    assert f"CONSULTA:\n{case['request']['question']}\n\nJSON:" in case["rag_prompt"]
known = cases[0]["response"]
assert "reflujo gastroesofágico" in known["rag_answer"]
known_source = next(source for source in known["sources"] if source["section"] == "Enfermedad" and "reflujo gastroesofágico" in source["text"])
assert source_label(known_source) in known["rag_answer"]
assert cases[1]["response"]["rag_answer"].rstrip(".") == "No hay información suficiente"
