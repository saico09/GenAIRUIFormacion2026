"""Comprueba incrementos y rutas de FastAPI o Spring Boot, sin modificar datos."""

import argparse
from urllib.error import HTTPError
from urllib.request import urlopen

from prometheus_client.parser import text_string_to_metric_families

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--service", choices=("fastapi", "springboot"), default="fastapi")
args = parser.parse_args()
if args.service == "springboot":
    BASE = "http://java-api:8080"
    METRICS_PATH = "/actuator/prometheus"
    ROUTE_LABEL = "uri"
    COUNTERS = ("http_server_requests_seconds_count",)
    BUCKET = "http_server_requests_seconds_bucket"
else:
    BASE = "http://localhost:8000"
    METRICS_PATH = "/metrics"
    ROUTE_LABEL = "route"
    COUNTERS = ("http_requests_total", "http_request_duration_seconds_count")
    BUCKET = "http_request_duration_seconds_bucket"


def get(path):
    try:
        with urlopen(BASE + path, timeout=15) as response:
            return response.status, response.read().decode()
    except HTTPError as error:
        return error.code, error.read().decode()


def samples(text):
    return [sample for family in text_string_to_metric_families(text) for sample in family.samples]


def count(items, name, status):
    expected = {"method": "GET", ROUTE_LABEL: "/patients/{id}", "status": status}
    return sum(
        sample.value for sample in items
        if sample.name == name and expected.items() <= sample.labels.items()
    )


code, body = get(METRICS_PATH)
assert code == 200
before = samples(body)
assert get("/patients/1")[0] == 200
assert get("/patients/999999")[0] == 404
code, body = get(METRICS_PATH)
assert code == 200
after = samples(body)
for status in ("200", "404"):
    for name in COUNTERS:
        assert count(after, name, status) == count(before, name, status) + 1, (name, status)
    assert any(
        s.name == BUCKET and s.labels.get(ROUTE_LABEL) == "/patients/{id}"
        and s.labels.get("status") == status for s in after
    )
assert not any(s.labels.get(ROUTE_LABEL) in ("/patients/1", "/patients/999999") for s in after)
print(body, end="")
