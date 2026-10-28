"""Envía el caso de Ana y coteja los cinco spans de Phoenix con los logs de Loki."""

import argparse
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from uuid import uuid4


def get_json(url):
    with urlopen(url, timeout=15) as response:
        return json.load(response)


def attribute(span, name):
    values = span["attributes"]
    if name in values:
        return values[name]
    for part in name.split("."):
        values = values[part]
    return values


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default="evidencias/s08/037-traza.json")
    parser.add_argument("--prefix", default="hdu037")
    args = parser.parse_args()
    dataset = Path(__file__).resolve().parents[1] / "datos" / "preguntas.json"
    case = json.loads(dataset.read_text(encoding="utf-8"))[0]
    request_id = f"{args.prefix}-{uuid4().hex}"
    request = Request("http://localhost:8000/chat", method="POST", headers={
        "Content-Type": "application/json", "X-Request-ID": request_id,
    }, data=json.dumps({"patient_id": case["patient_id"], "question": case["question"]}).encode())
    with urlopen(request, timeout=250) as response:
        assert response.status == 200 and response.headers["X-Request-ID"] == request_id
        chat = json.load(response)
    assert case["expected"] in chat["rag_answer"]
    assert "[paciente-1.md/Enfermedad]" in chat["rag_answer"]

    spans_url = "http://localhost:6006/v1/projects/genai/spans?" + urlencode({
        "attribute": f"request_id:{request_id}", "limit": 100,
    })
    deadline = time.monotonic() + 60
    while True:
        spans = get_json(spans_url)["data"]
        if len(spans) >= 5:
            break
        if time.monotonic() >= deadline:
            raise RuntimeError(f"Phoenix recibió {len(spans)} de los cinco spans en 60 s")
        time.sleep(1)
    assert len(spans) == 5
    roots = [span for span in spans if not span["parent_id"]]
    assert len(roots) == 1 and roots[0]["name"] == "rag"
    root = roots[0]
    trace_id = root["context"]["trace_id"]
    all_spans = get_json("http://localhost:6006/v1/projects/genai/spans?" + urlencode({
        "trace_id": trace_id, "limit": 100,
    }))["data"]
    assert len(all_spans) == 5
    children = sorted((span for span in spans if span is not root), key=lambda span: span["start_time"])
    assert [span["name"] for span in children] == ["retrieval", "prompt", "llamada_llm", "respuesta"]
    durations = {}
    for span in spans:
        assert span["context"]["trace_id"] == trace_id
        assert attribute(span, "request_id") == request_id
        assert span["status_code"] == "OK"
        start, end = (datetime.fromisoformat(span[key]) for key in ("start_time", "end_time"))
        durations[span["name"]] = (end - start).total_seconds() * 1000
        assert durations[span["name"]] > 0
    for previous, following in zip(children, children[1:]):
        assert previous["end_time"] <= following["start_time"]
    inputs, outputs = {}, {}
    for span in children:
        assert span["parent_id"] == root["context"]["span_id"]
        assert root["start_time"] <= span["start_time"] <= span["end_time"] <= root["end_time"]
        assert attribute(span, "input.mime_type") == attribute(span, "output.mime_type") == "application/json"
        inputs[span["name"]] = json.loads(attribute(span, "input.value"))
        outputs[span["name"]] = json.loads(attribute(span, "output.value"))
    assert inputs["retrieval"] == {"patient_id": case["patient_id"], "pregunta": case["question"]}
    fragments = outputs["retrieval"]["fragmentos"]
    assert fragments == chat["sources"] and all(fragment["patient_id"] == case["patient_id"] for fragment in fragments)
    assert inputs["prompt"] == {"pregunta": case["question"], "fragmentos": fragments}
    prompt = outputs["prompt"]["prompt"]
    assert case["question"] in prompt and all(fragment["text"] in prompt for fragment in fragments)
    assert inputs["llamada_llm"] == {"prompt": prompt}
    assert outputs["llamada_llm"] == inputs["respuesta"] == outputs["respuesta"] == {"respuesta": chat["rag_answer"]}
    llm_span = children[2]
    assert llm_span["span_kind"] == "LLM" and children[0]["span_kind"] == "RETRIEVER"
    assert json.loads(attribute(llm_span, "llm.invocation_parameters")) == {"temperature": 0, "num_ctx": 2048, "num_predict": 256}

    query = f'{{service="fastapi"}} | json | request_id="{request_id}"'
    deadline = time.monotonic() + 60
    while True:
        end = time.time_ns()
        data = get_json("http://localhost:3100/loki/api/v1/query_range?" + urlencode({
            "query": query, "start": end - 3600_000_000_000, "end": end,
            "direction": "forward", "limit": 100,
        }))
        assert data["status"] == "success"
        events = [json.loads(line) for stream in data["data"]["result"] for _, line in stream["values"]]
        if any(event["event"] == "http" for event in events):
            break
        if time.monotonic() >= deadline:
            raise RuntimeError("No llegó el evento HTTP a Loki en 60 s")
        time.sleep(1)
    events.sort(key=lambda event: event["timestamp"])
    assert len(events) == 7 and all(event["request_id"] == request_id for event in events)
    assert [event["node"] for event in events if event["event"] == "rag_node"] == [span["name"] for span in children]
    calls = [event for event in events if event["event"] == "llm"]
    assert len(calls) == 2
    branches = {event["branch"]: event for event in calls}
    assert set(branches) == {"direct", "rag"}
    assert branches["direct"]["model"] == branches["rag"]["model"] == attribute(llm_span, "llm.model_name")
    assert branches["direct"]["prompt"] == case["question"] and branches["rag"]["prompt"] == prompt
    for branch, event in branches.items():
        assert event["status"] == "ok" and event["response"] == chat[f"{branch}_answer"]
    assert any(event["event"] == "http" and event["status"] == 200 for event in events)

    result = {
        "checked_at": datetime.now(timezone.utc).isoformat(), "request_id": request_id,
        "trace_id": trace_id, "url": f"http://localhost:6006/redirects/traces/{trace_id}",
        "question": case["question"], "patient_id": case["patient_id"], "response": chat,
        "spans_url": spans_url, "spans": [root, *children], "node_durations_ms": durations,
        "loki": {"query": query, "logs": events},
        "checks": {"single_root_rag": True, "four_children_in_order": True,
                   "same_request_id": True, "inputs_outputs_match": True,
                   "loki_matches": True, "durations_positive": True},
    }
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"OK raíz y cuatro hijos, entradas/salidas, duración y siete logs: {request_id}")
    print(result["url"])


if __name__ == "__main__":
    main()
