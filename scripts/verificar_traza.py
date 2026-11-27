"""Pregunta por un paciente temporal y coteja los cinco spans de Phoenix con los logs de Loki."""

import argparse
import json
import sys
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python-api"))
from rag import source_label, validate_direct_answer, validate_rag_answer

API = "http://localhost:8000"
NAME = "Elena Prueba"
OUTPUT = ROOT / ".local" / "verificaciones" / f"{Path(__file__).stem}-{datetime.now():%Y%m%dT%H%M%S}.json"


def get_json(url):
    with urlopen(url, timeout=15) as response:
        return json.load(response)


def call(method, url, body=None, headers=None, timeout=30):
    data = None if body is None else json.dumps(body, ensure_ascii=False).encode("utf-8")
    request = Request(url, data=data, method=method,
                      headers={"Content-Type": "application/json", **(headers or {})})
    with urlopen(request, timeout=timeout) as response:
        raw = response.read()
        return response.status, response.headers, json.loads(raw) if raw else None


@contextmanager
def temporary_patient():
    seed = json.loads((ROOT / "datos" / "casos_clinicos.json").read_text(encoding="utf-8"))["cases"][0]
    record = {field: seed[field].replace(seed["name"], NAME) for field in ("disease", "treatment", "medication")}
    _, _, patient = call("POST", f"{API}/patients", {
        "name": NAME, "birth_date": seed["birth_date"], "email": "elena.prueba@example.com"})
    try:
        call("POST", f"{API}/patients/{patient['id']}/diseases", record)
        yield patient
    finally:
        # Borra fila e informe; la sincronización quita después sus puntos de Qdrant.
        call("DELETE", f"{API}/patients/{patient['id']}")
        _, _, sync = call("POST", f"{API}/clinical/patients/{patient['id']}/sync", timeout=180)
        assert sync["status"] == "removed", sync


def send_chat(patient_id, question, request_id):
    """Un X-Execution-ID fijo: si el cliente corta y reintenta, la API devuelve la misma consulta."""
    headers = {"X-Request-ID": request_id, "X-Execution-ID": str(uuid4())}
    body = {"patient_id": patient_id, "question": question}
    try:
        # Dos llamadas LLM de hasta 180 s cada una.
        return call("POST", f"{API}/chat", body, headers, timeout=420)
    except TimeoutError:
        return call("POST", f"{API}/chat", body, headers, timeout=420)


def attribute(span, name):
    values = span["attributes"]
    if name in values:
        return values[name]
    for part in name.split("."):
        values = values[part]
    return values


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    parser.add_argument("--prefix", default="hdu037")
    parser.add_argument("--patient-id", type=int, help="Paciente ya creado, en lugar del temporal")
    parser.add_argument("--question")
    parser.add_argument("--expected")
    args = parser.parse_args()
    if args.patient_id is not None:
        if not args.question or not args.expected:
            parser.error("--patient-id requiere --question y --expected")
        verify({"patient_id": args.patient_id, "question": args.question, "expected": args.expected}, args)
        return
    case = json.loads((ROOT / "datos" / "preguntas.json").read_text(encoding="utf-8"))[0]
    with temporary_patient() as patient:
        verify({"patient_id": patient["id"], "question": case["question"].replace("Ana Demo", NAME),
                "expected": case["expected"]}, args)


def verify(case, args):
    request_id = f"{args.prefix}-{uuid4().hex}"
    status, headers, chat = send_chat(case["patient_id"], case["question"], request_id)
    assert status == 200 and headers["X-Request-ID"] == request_id
    assert case["expected"] in chat["rag_answer"]
    history = get_json(f"http://localhost:8080/patients/{case['patient_id']}/history")
    assert 1 <= len(chat["sources"]) <= 9
    known_source = next(source for source in chat["sources"] if source["section"] == "Enfermedad" and case["expected"] in source["text"])
    assert known_source["source"] == history["filename"]
    assert any(entry["id"] == known_source["record_id"] and entry["disease"] == known_source["text"] for entry in history["entries"])
    assert source_label(known_source) in chat["rag_answer"]

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
    assert 1 <= len(fragments) <= 3 and all(fragment["patient_id"] == case["patient_id"] for fragment in fragments)
    assert inputs["prompt"] == {"pregunta": case["question"], "fragmentos": fragments}
    prompt = outputs["prompt"]["prompt"]
    # El prompt lleva los registros recuperados completos, no sólo los fragmentos.
    context = outputs["prompt"]["contexto"]
    assert context == chat["sources"]
    assert all(fragment in context for fragment in fragments)
    assert all(item["patient_id"] == case["patient_id"] for item in context)
    assert case["question"] in prompt and all(item["text"] in prompt and source_label(item) in prompt for item in context)
    assert inputs["llamada_llm"] == {"prompt": prompt}
    assert outputs["llamada_llm"] == inputs["respuesta"]
    raw_rag = outputs["llamada_llm"]["respuesta"]
    assert outputs["respuesta"] == {"respuesta": validate_rag_answer(raw_rag, context, case["question"])} == {"respuesta": chat["rag_answer"]}
    llm_span = children[2]
    assert llm_span["span_kind"] == "LLM" and children[0]["span_kind"] == "RETRIEVER"
    expected_options = {"temperature": 0.2, "num_ctx": 8192, "num_predict": 1536, "top_p": 0.9, "top_k": 20,
                        "min_p": 0, "presence_penalty": 0, "repeat_penalty": 1, "draft_num_predict": 0}
    assert json.loads(attribute(llm_span, "llm.invocation_parameters")) == {**expected_options, "think": False}

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
    # Cada rama puede repetir una vez la generación (evento llm_retry y otra llamada llm).
    retries = [event for event in events if event["event"] == "llm_retry"]
    assert len(retries) <= 2 and len(events) == 7 + 2 * len(retries)
    assert all(event["request_id"] == request_id for event in events)
    assert [event["node"] for event in events if event["event"] == "rag_node"] == [span["name"] for span in children]
    calls = [event for event in events if event["event"] == "llm"]
    assert len(calls) == 2 + len(retries)
    branches = {event["branch"]: event for event in calls if event["status"] == "ok"}
    assert set(branches) == {"direct", "rag"}
    assert branches["direct"]["model"] == branches["rag"]["model"] == attribute(llm_span, "llm.model_name")
    assert branches["direct"]["prompt"] == case["question"] and branches["rag"]["prompt"] == prompt
    for branch, event in branches.items():
        assert event["status"] == "ok"
        if branch == "rag":
            assert event["response"] == raw_rag
        else:
            assert validate_direct_answer(event["response"], case["question"]) == chat["direct_answer"]
        assert event["model_options"] == expected_options and event["think_requested"] is False
        assert type(event["thinking_returned"]) is bool and "thinking" not in event
    assert any(event["event"] == "http" and event["status"] == 200 for event in events)

    result = {
        "checked_at": datetime.now(timezone.utc).isoformat(), "request_id": request_id,
        "trace_id": trace_id, "url": f"http://localhost:6006/redirects/traces/{trace_id}",
        "question": case["question"], "patient_id": case["patient_id"], "response": chat,
        "spans_url": spans_url, "spans": [root, *children], "node_durations_ms": durations,
        "loki": {"query": query, "logs": events},
        "checks": {"single_root_rag": True, "four_children_in_order": True,
                   "same_request_id": True, "inputs_outputs_match": True,
                   "loki_matches": True, "durations_positive": True,
                   "rag_raw_to_validated_http": True, "direct_raw_to_validated_http": True},
    }
    output = args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"OK raíz y cuatro hijos, entradas/salidas, duración y siete logs: {request_id}")
    print(result["url"])


if __name__ == "__main__":
    main()
