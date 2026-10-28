"""Pregunta por Ana y comprueba en Loki las dos llamadas LLM de la petición."""

import argparse
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from uuid import uuid4

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--output", default="evidencias/s07/032-llm.json")
parser.add_argument("--prefix", default="hdu032")
args = parser.parse_args()
question = "¿Cuál es el diagnóstico de Ana?"
request_id = f"{args.prefix}-{uuid4().hex}"
start = time.time_ns() - 120_000_000_000
request = Request("http://127.0.0.1:8000/chat", method="POST",
                  headers={"Content-Type": "application/json", "X-Request-ID": request_id},
                  data=json.dumps({"patient_id": 1, "question": question}).encode())
with urlopen(request, timeout=300) as response:
    assert response.status == 200
    assert response.headers["X-Request-ID"] == request_id
    answer = json.load(response)
assert "Enfermedad Alfa" in answer["rag_answer"] and "[paciente-1.md/Enfermedad]" in answer["rag_answer"]
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
assert len(llm) == 2 and len(http) == 1
assert http[0]["status"] == 200 and http[0]["route"] == "/chat"
branches = {event["branch"]: event for event in llm}
assert set(branches) == {"direct", "rag"}
assert branches["direct"]["prompt"] == question
assert branches["direct"]["model"] == branches["rag"]["model"]
assert all(source["patient_id"] == 1 for source in answer["sources"])
for source in answer["sources"]:
    assert source["text"] in branches["rag"]["prompt"]
assert "CONTEXTO:" in branches["rag"]["prompt"] and question in branches["rag"]["prompt"]
for branch, event in branches.items():
    assert event["request_id"] == request_id and event["status"] == "ok"
    assert event["response"] == answer[f"{branch}_answer"]
    assert isinstance(event["duration_ms"], (int, float)) and event["duration_ms"] > 0

def utc(value):
    return datetime.fromtimestamp(value / 1_000_000_000, timezone.utc).isoformat()

output = Path(args.output)
output.parent.mkdir(parents=True, exist_ok=True)
output.write_text(json.dumps({"checked_at": utc(time.time_ns()), "request_id": request_id,
                             "patient_id": 1, "question": question, "answer": answer,
                             "http_log": http[0], "checks": [{"name": "llm", "service": "fastapi",
                             "query": query + ' | event="llm"', "start_utc": utc(start),
                             "end_utc": utc(end), "logs": llm}]}, ensure_ascii=False, indent=2) + "\n",
                  encoding="utf-8")
print(f"OK {request_id}: dos ramas, mismo modelo, contexto solo en RAG, respuesta y duración en Loki; {output}")
