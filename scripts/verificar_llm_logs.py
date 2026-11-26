"""Pregunta por un paciente temporal y comprueba en Loki las dos llamadas LLM de la petición."""

import argparse
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import urlopen
from uuid import uuid4

# verificar_traza agrega python-api al path: debe importarse antes que app y rag.
from verificar_traza import NAME, ROOT, send_chat, temporary_patient
from app.knowledge import record_context
from rag import source_label, validate_direct_answer, validate_rag_answer

OUTPUT = ROOT / ".local" / "verificaciones" / f"{Path(__file__).stem}-{datetime.now():%Y%m%dT%H%M%S}.json"


def utc(value):
    return datetime.fromtimestamp(value / 1_000_000_000, timezone.utc).isoformat()


def verify(patient_id, args):
    question = f"¿Cuál es el diagnóstico de {NAME}?"
    request_id = f"{args.prefix}-{uuid4().hex}"
    start = time.time_ns() - 120_000_000_000
    status, headers, answer = send_chat(patient_id, question, request_id)
    assert status == 200
    assert headers["X-Request-ID"] == request_id
    with urlopen(f"http://127.0.0.1:8080/patients/{patient_id}/history", timeout=15) as response:
        history = json.load(response)
    assert len(answer["sources"]) == 3
    known_source = next(source for source in answer["sources"] if source["section"] == "Enfermedad" and "reflujo gastroesofágico" in source["text"])
    assert known_source["source"] == history["filename"]
    assert any(entry["id"] == known_source["record_id"] and entry["disease"] == known_source["text"] for entry in history["entries"])
    assert "reflujo gastroesofágico" in answer["rag_answer"] and source_label(known_source) in answer["rag_answer"]
    query = f'{{service="fastapi"}} | json | request_id="{request_id}"'
    deadline = time.monotonic() + 60
    while True:
        end = time.time_ns()
        parameters = urlencode({"query": query, "start": start, "end": end,
                                "direction": "forward", "limit": 100})
        with urlopen("http://127.0.0.1:3100/loki/api/v1/query_range?" + parameters, timeout=15) as response:
            result = json.load(response)
        assert result["status"] == "success"
        events = [json.loads(line) for stream in result["data"]["result"] for _, line in stream["values"]]
        llm = [event for event in events if event["event"] == "llm"]
        http = [event for event in events if event["event"] == "http"]
        if len(llm) >= 2 and http:
            break
        if time.monotonic() >= deadline:
            raise RuntimeError("Faltan eventos LLM/HTTP en Loki después de 60 segundos")
        time.sleep(1)
    assert len(http) == 1
    assert http[0]["status"] == 200 and http[0]["route"] == "/chat"
    # Cada rama tiene a lo sumo un reintento (evento llm_retry); vale la última llamada correcta.
    retries = [event for event in events if event.get("event") == "llm_retry"]
    assert len(llm) == 2 + len(retries) and len(retries) <= 2
    branches = {event["branch"]: event for event in llm if event["status"] == "ok"}
    assert set(branches) == {"direct", "rag"}
    assert branches["direct"]["prompt"] == question
    assert branches["direct"]["model"] == branches["rag"]["model"]
    assert all(source["patient_id"] == patient_id for source in answer["sources"])
    # El prompt lleva los registros recuperados completos, no sólo los fragmentos.
    context = record_context(patient_id, answer["sources"])
    for source in context:
        assert source["text"] in branches["rag"]["prompt"]
        assert source_label(source) in branches["rag"]["prompt"]
    assert "CONTEXTO:" in branches["rag"]["prompt"] and question in branches["rag"]["prompt"]
    for branch, event in branches.items():
        assert event["request_id"] == request_id and event["status"] == "ok"
        displayed = (validate_rag_answer(event["response"], context, question) if branch == "rag"
                     else validate_direct_answer(event["response"], question))
        assert displayed == answer[f"{branch}_answer"]
        assert isinstance(event["duration_ms"], (int, float)) and event["duration_ms"] > 0

    output = args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps({"checked_at": utc(time.time_ns()), "request_id": request_id,
                                 "patient_id": patient_id, "question": question, "answer": answer,
                                 "rag_raw_to_http_checked": True,
                                 "http_log": http[0], "checks": [{"name": "llm", "service": "fastapi",
                                 "query": query + ' | event="llm"', "start_utc": utc(start),
                                 "end_utc": utc(end), "logs": llm}]}, ensure_ascii=False, indent=2) + "\n",
                      encoding="utf-8")
    print(f"OK {request_id}: dos ramas, mismo modelo, contexto solo en RAG, respuesta y duración en Loki; {output}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    parser.add_argument("--prefix", default="hdu032")
    args = parser.parse_args()
    with temporary_patient() as patient:
        verify(patient["id"], args)


if __name__ == "__main__":
    main()
