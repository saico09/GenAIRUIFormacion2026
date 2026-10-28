"""Genera cuatro GET y encuentra sus logs en Loki por servicio y request_id."""

import argparse
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from uuid import uuid4

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--output", default="evidencias/s07/031-loki.json")
args = parser.parse_args()


def loki(path, parameters):
    url = "http://127.0.0.1:3100/loki/api/v1/" + path + "?" + urlencode(parameters)
    with urlopen(url, timeout=15) as response:
        result = json.load(response)
    assert result["status"] == "success", result
    return result["data"]


def utc(nanoseconds):
    return datetime.fromtimestamp(nanoseconds / 1_000_000_000, timezone.utc).isoformat()


run_id = uuid4().hex
start = time.time_ns() - 120_000_000_000  # Margen para el reloj del contenedor.
checks = []
for service, port in (("fastapi", 8000), ("springboot", 8080)):
    responses = []
    for patient_id, expected in ((1, 200), (999999, 404)):
        request_id = f"hdu031-{service}-{expected}-{run_id}"
        request = Request(f"http://127.0.0.1:{port}/patients/{patient_id}",
                          headers={"X-Request-ID": request_id})
        try:
            response = urlopen(request, timeout=15)
        except HTTPError as error:
            response = error
        with response:
            assert response.code == expected
            assert response.headers.get("X-Request-ID") == request_id
            response.read()  # No guardar cuerpos ni datos de pacientes.
        responses.append({"status": expected, "request_id": request_id})
    query = (f'{{service="{service}"}} | json | event="http" '
             f'| request_id=~"hdu031-{service}-(200|404)-{run_id}"')
    checks.append({"service": service, "responses": responses, "query": query})

deadline = time.monotonic() + 60
for check in checks:
    while True:
        end = time.time_ns()
        data = loki("query_range", {"query": check["query"], "start": start,
                                   "end": end, "direction": "forward", "limit": 100})
        events = [json.loads(line) for stream in data["result"] for _, line in stream["values"]]
        if len(events) >= 2:
            break
        if time.monotonic() >= deadline:
            raise RuntimeError(f"Loki no recibió los dos logs de {check['service']} en 60 segundos")
        time.sleep(1)
    assert len(events) == 2, (check["service"], len(events))
    for response in check["responses"]:
        matches = [event for event in events if event.get("request_id") == response["request_id"]]
        assert len(matches) == 1
        event = matches[0]
        assert event["service"] == check["service"] and event["event"] == "http"
        assert event["method"] == "GET" and event["route"] == "/patients/{id}"
        assert event["status"] == response["status"]
        assert isinstance(event["duration_ms"], (int, float)) and event["duration_ms"] >= 0
    check.update({"start_utc": utc(start), "end_utc": utc(end), "logs": events})

# Consultar etiquetas almacenadas, sin el parser JSON de la consulta anterior.
series = loki("series", {"match[]": '{service=~".+"}', "start": start, "end": time.time_ns()})
assert {stream["service"] for stream in series} == {"fastapi", "springboot"}, series
assert all("request_id" not in stream for stream in series), series
output = Path(args.output)
output.parent.mkdir(parents=True, exist_ok=True)
output.write_text(json.dumps({"checked_at": utc(time.time_ns()), "checks": checks,
                              "stored_stream_labels": series}, ensure_ascii=False, indent=2) + "\n",
                  encoding="utf-8")
print(f"OK cuatro logs correlacionados en Loki; solo fastapi/springboot, request_id fuera de etiquetas; {output}")
