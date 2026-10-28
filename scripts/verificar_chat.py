"""Prueba la comparación real con Ollama; ejecutar en python-api por stdin."""

import json
from pathlib import Path

from app.knowledge import request_json
from app.llm import CHAT_MODEL, TEMPERATURE, TIMEOUT_SECONDS
from rag import build_rag_prompt

questions = json.loads(Path("/datos/preguntas.json").read_text(encoding="utf-8"))
cases = []
for question in (questions[0], questions[3]):
    body = {key: question[key] for key in ("patient_id", "question")}
    response = request_json("POST", "http://localhost:8000/chat", body, timeout=360)
    cases.append({
        "request": body,
        "direct_prompt": body["question"],
        "rag_prompt": build_rag_prompt(body["question"], response["sources"]),
        "response": response,
    })
print(json.dumps({
    "model": CHAT_MODEL, "temperature": TEMPERATURE, "num_ctx": 2048,
    "num_predict": 256, "timeout_seconds_per_llm_call": TIMEOUT_SECONDS,
    "cases": cases,
}, ensure_ascii=False, indent=2))

for case in cases:
    response = case["response"]
    assert isinstance(response["direct_answer"], str) and response["direct_answer"].strip()
    assert len(response["sources"]) == 2
    assert all(source["patient_id"] == 1 for source in response["sources"])
    assert case["direct_prompt"] == case["request"]["question"]
    assert f"PREGUNTA:\n{case['request']['question']}\n\nRESPUESTA:" in case["rag_prompt"]
known = cases[0]["response"]
assert "Enfermedad Alfa" in known["rag_answer"]
assert "[paciente-1.md/Enfermedad]" in known["rag_answer"]
assert any(source["source"] == "paciente-1.md" and source["section"] == "Enfermedad"
           and "Enfermedad Alfa" in source["text"] for source in known["sources"])
assert cases[1]["response"]["rag_answer"].rstrip(".") == "No hay información suficiente"
