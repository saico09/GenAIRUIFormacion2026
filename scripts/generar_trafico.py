"""20 GET válidos y 5 ausentes por API, distribuidos en dos minutos."""

import argparse
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import urlopen

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--output", default="evidencias/s06/028-peticiones.json")
args = parser.parse_args()
requests = []
start = time.monotonic()
try:
    for index in range(25):
        time.sleep(max(0, start + index * 5 - time.monotonic()))
        patient_id = 999999 if index % 5 == 4 else 1
        for service, port in (("fastapi", 8000), ("springboot", 8080)):
            timestamp = datetime.now(timezone.utc).isoformat()
            tick = time.monotonic()
            try:
                with urlopen(f"http://localhost:{port}/patients/{patient_id}", timeout=15) as response:
                    status = response.status
            except HTTPError as error:
                status = error.code
                error.close()
            requests.append({
                "service": service, "time": timestamp, "patient_id": patient_id,
                "status": status, "duration_ms": round((time.monotonic() - tick) * 1000, 3),
            })
            assert status == (404 if patient_id == 999999 else 200), requests[-1]
finally:
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(requests, indent=2) + "\n", encoding="utf-8")

assert len(requests) == 50
for service in ("fastapi", "springboot"):
    assert sum(r["service"] == service and r["status"] == 200 for r in requests) == 20
    assert sum(r["service"] == service and r["status"] == 404 for r in requests) == 5
print(f"OK 50 peticiones en {time.monotonic() - start:.1f} s; {args.output}")
