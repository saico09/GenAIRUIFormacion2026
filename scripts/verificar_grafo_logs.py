"""Coteja los casos reales del navegador con los cuatro nodos y las dos llamadas en Loki."""

import argparse
import json
import time
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import urlopen

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("input", help="JSON de resultados de verificar_chat_ui.cjs")
parser.add_argument("--output", default="evidencias/s08/035-correlacion.json")
args = parser.parse_args()
cases = json.loads(Path(args.input).read_text(encoding="utf-8"))
checks = []
for case in cases:
    request_id = case["request_id"]
    assert request_id
    query = f'{{service="fastapi"}} | json | request_id="{request_id}"'
    deadline = time.monotonic() + 60
    while True:
        end = time.time_ns()
        parameters = urlencode({"query": query, "start": end - 3600_000_000_000,
                                "end": end, "direction": "forward", "limit": 100})
        with urlopen("http://127.0.0.1:3100/loki/api/v1/query_range?" + parameters, timeout=15) as response:
            data = json.load(response)
        assert data["status"] == "success"
        events = [json.loads(line) for stream in data["data"]["result"] for _, line in stream["values"]]
        if any(event["event"] == "http" for event in events):
            break
        if time.monotonic() >= deadline:
            raise RuntimeError(f"No llegó el evento HTTP de {request_id}")
        time.sleep(1)
    events.sort(key=lambda event: event["timestamp"])
    nodes = [event for event in events if event["event"] == "rag_node"]
    assert [event["node"] for event in nodes] == ["retrieval", "prompt", "llamada_llm", "respuesta"]
    assert all(event["request_id"] == request_id for event in events)
    calls = [event for event in events if event["event"] == "llm"]
    assert len(calls) == 2
    branches = {event["branch"]: event for event in calls}
    assert set(branches) == {"direct", "rag"}
    assert branches["direct"]["model"] == branches["rag"]["model"]
    assert branches["direct"]["prompt"] == case["question"]
    assert case["question"] in branches["rag"]["prompt"]
    assert all(source["text"] in branches["rag"]["prompt"] for source in case["sources"])
    for branch, event in branches.items():
        assert event["response"] == case[f"{branch}_answer"] and event["status"] == "ok"
    assert any(event["event"] == "http" and event["status"] == 200 for event in events)
    checks.append({"request_id": request_id, "question": case["question"], "query": query,
                   "nodes": [event["node"] for event in nodes], "logs": events})
output = Path(args.output)
output.parent.mkdir(parents=True, exist_ok=True)
output.write_text(json.dumps({"checks": checks}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(f"OK {len(checks)} consultas: cuatro nodos en orden, dos ramas, mismo request_id/modelo/pregunta")
