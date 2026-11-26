"""Prueba la comparación real con Ollama; ejecutar en python-api por stdin."""

import json
from pathlib import Path
from urllib.request import Request, urlopen
from uuid import uuid4, uuid5

from app.llm import CHAT_MODEL, MODEL_OPTIONS, TIMEOUT_SECONDS
from app.history_documents import fragments_from_history, parse_history
from rag import source_label

API = "http://localhost:8000"
NAME = "Elena Prueba"
RUN = uuid4()


def call(method, path, body=None, headers=None, timeout=30):
    data = None if body is None else json.dumps(body, ensure_ascii=False).encode("utf-8")
    request = Request(API + path, data=data, method=method,
                      headers={"Content-Type": "application/json", **(headers or {})})
    with urlopen(request, timeout=timeout) as response:
        raw = response.read()
        return json.loads(raw) if raw else None


def chat(body):
    # Un X-Execution-ID fijo por pregunta: si se corta y se reintenta, la API devuelve la misma consulta.
    headers = {"X-Execution-ID": str(uuid5(RUN, body["question"]))}
    try:
        return call("POST", "/chat", body, headers, timeout=2 * TIMEOUT_SECONDS + 60)
    except TimeoutError:
        return call("POST", "/chat", body, headers, timeout=2 * TIMEOUT_SECONDS + 60)


def known_payloads(patient_id):
    # Se relee en cada pregunta: la consulta anterior también queda en el informe.
    path = next(Path("/datos/historias").glob(f"paciente-{patient_id}-*.md"))
    with path.open(encoding="utf-8", newline="") as stream:
        return [fragment["payload"] for fragment in fragments_from_history(parse_history(stream.read(), path.name))]


seed = json.loads(Path("/datos/casos_clinicos.json").read_text(encoding="utf-8"))["cases"][0]
questions = json.loads(Path("/datos/preguntas.json").read_text(encoding="utf-8"))
patient = call("POST", "/patients", {"name": NAME, "birth_date": seed["birth_date"], "email": "elena.prueba@example.com"})
cases = []
try:
    call("POST", f"/patients/{patient['id']}/diseases",
         {field: seed[field].replace(seed["name"], NAME) for field in ("disease", "treatment", "medication")})
    for question in (questions[0], questions[3]):
        body = {"patient_id": patient["id"], "question": question["question"].replace(seed["name"], NAME)}
        payloads = known_payloads(patient["id"])
        response = chat(body)
        cases.append({
            "request": body,
            "response": response,
            "known_payloads": payloads,
        })
finally:
    # Borra fila e informe; la sincronización quita después sus puntos de Qdrant.
    call("DELETE", f"/patients/{patient['id']}")
    assert call("POST", f"/clinical/patients/{patient['id']}/sync", timeout=180)["status"] == "removed"
print(json.dumps({
    "model": CHAT_MODEL, **MODEL_OPTIONS, "timeout_seconds_per_llm_call": TIMEOUT_SECONDS,
    "temporary_patient": patient, "cases": cases,
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
known = cases[0]["response"]
assert "reflujo gastroesofágico" in known["rag_answer"]
known_source = next(source for source in known["sources"] if source["section"] == "Enfermedad" and "reflujo gastroesofágico" in source["text"])
assert source_label(known_source) in known["rag_answer"]
assert cases[1]["response"]["rag_answer"].rstrip(".") == "No hay información suficiente"
