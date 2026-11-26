"""Métricas HTTP: una serie por ruta, nunca una serie por paciente."""

from time import perf_counter

from fastapi import FastAPI, Request, Response
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest

from app.observability import route_template

REQUESTS = Counter("http_requests_total", "Peticiones HTTP recibidas", ("method", "route", "status"))
# Los buckets por defecto llegan a 10 s; /chat tarda de 15 s a varios minutos.
BUCKETS = (0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10, 20, 30, 60, 90, 120, 180, 240, 300)
DURATION = Histogram(
    "http_request_duration_seconds", "Duración HTTP en segundos", ("method", "route", "status"),
    buckets=BUCKETS,
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
            route = route_template(request.scope)
            labels = (request.method, route, str(status))
            REQUESTS.labels(*labels).inc()
            DURATION.labels(*labels).observe(perf_counter() - start)

    @app.get("/metrics", include_in_schema=False)
    def metrics():
        return Response(generate_latest(), headers={"Content-Type": CONTENT_TYPE_LATEST})
