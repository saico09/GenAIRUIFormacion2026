"""Coteja cuatro respuestas HTTP con sus eventos JSON de Docker Compose."""

import json
import subprocess
from datetime import datetime
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from uuid import UUID, uuid4

results = []
for service, container, port in (("fastapi", "python-api", 8000), ("springboot", "java-api", 8080)):
    responses = []
    for patient_id, expected in ((1, 200), (999999, 404)):
        supplied = f"hdu030-{service}-{uuid4()}" if expected == 200 else None
        request = Request(f"http://127.0.0.1:{port}/patients/{patient_id}",
                          headers={"X-Request-ID": supplied} if supplied else {})
        try:
            response = urlopen(request, timeout=15)
        except HTTPError as error:
            response = error
        with response:
            status = response.code
            request_id = response.headers.get("X-Request-ID")
            body = json.load(response)
        assert status == expected, (service, status)
        if supplied:
            assert request_id == supplied
        else:
            UUID(request_id)
        responses.append({"url": request.full_url, "status": status,
                          "X-Request-ID": request_id, "body": body})
    command = subprocess.run([
        "docker", "compose", "logs", "--no-color", "--no-log-prefix", "--since", "2m", container,
    ], check=True, capture_output=True, text=True, encoding="utf-8")
    logs = []
    for line in command.stdout.splitlines():
        try:
            event = json.loads(line)
            if isinstance(event, dict):
                logs.append(event)
        except json.JSONDecodeError:
            pass  # Los mensajes de arranque del runtime no son eventos de petición.
    for response in responses:
        matches = [entry for entry in logs if entry.get("request_id") == response["X-Request-ID"]]
        assert len(matches) == 1, (service, response["X-Request-ID"], len(matches))
        event = matches[0]
        assert event["service"] == service and event["event"] == "http"
        assert event["method"] == "GET" and event["route"] == "/patients/{id}"
        assert event["status"] == response["status"]
        assert isinstance(event["duration_ms"], (int, float)) and event["duration_ms"] >= 0
        assert datetime.fromisoformat(event["timestamp"].replace("Z", "+00:00")).tzinfo is not None
        results.append({"response": response, "log": event})

output = Path("evidencias/s07/logs-apis.txt")
output.parent.mkdir(parents=True, exist_ok=True)
output.write_text(json.dumps(results, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(f"OK cuatro respuestas con su mismo request_id y un evento JSON cada una; {output}")
