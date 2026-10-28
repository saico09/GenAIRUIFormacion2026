"""Métricas HTTP: una serie por ruta, nunca una serie por paciente."""

from time import perf_counter

from fastapi import FastAPI, Request, Response
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest

REQUESTS = Counter("http_requests_total", "Peticiones HTTP recibidas", ("method", "route", "status"))
DURATION = Histogram(
    "http_request_duration_seconds", "Duración HTTP en segundos", ("method", "route", "status"),
)


def install_metrics(app: FastAPI) -> None:
    @app.middleware("http")
    async def measure_request(request: Request, call_next):
        start = perf_counter()
        status = 500
        try:
            response = await call_next(request)
            status = response.status_code
            return response
        finally:
            route = getattr(request.scope.get("route"), "path", "unmatched")
            route = route.replace("{patient_id}", "{id}")
            labels = (request.method, route, str(status))
            REQUESTS.labels(*labels).inc()
            DURATION.labels(*labels).observe(perf_counter() - start)

    @app.get("/metrics", include_in_schema=False)
    def metrics():
        return Response(generate_latest(), headers={"Content-Type": CONTENT_TYPE_LATEST})
