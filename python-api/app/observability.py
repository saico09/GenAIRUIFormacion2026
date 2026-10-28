"""Identificador de petición y eventos JSON para seguir una consulta."""

import json
import logging
import re
import sys
from contextvars import ContextVar
from datetime import datetime, timezone
from time import perf_counter
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

request_id_context: ContextVar[str | None] = ContextVar("request_id", default=None)
logger = logging.getLogger("genai_json")
logger.setLevel(logging.INFO)
logger.propagate = False
if not logger.handlers:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter("%(message)s"))
    logger.addHandler(handler)


def log_event(event: str, **fields) -> None:
    logger.info(json.dumps({
        "timestamp": datetime.now(timezone.utc).isoformat(), "service": "fastapi",
        "event": event, "request_id": request_id_context.get(), **fields,
    }, ensure_ascii=False))


def install_request_logging(app: FastAPI) -> None:
    @app.exception_handler(Exception)
    async def internal_error(request: Request, error: Exception):
        # Starlette construye el 500 fuera del middleware: conserva también allí el id.
        return JSONResponse(status_code=500, content={"detail": "Error interno"},
                            headers={"X-Request-ID": request.state.request_id})

    @app.middleware("http")
    async def log_request(request: Request, call_next):
        supplied = request.headers.get("X-Request-ID", "")
        request_id = supplied if re.fullmatch(r"[A-Za-z0-9._:-]{1,128}", supplied) else str(uuid4())
        request.state.request_id = request_id
        token = request_id_context.set(request_id)
        start = perf_counter()
        status = 500
        try:
            response = await call_next(request)
            status = response.status_code
            response.headers["X-Request-ID"] = request_id
            return response
        finally:
            route = getattr(request.scope.get("route"), "path", "unmatched").replace("{patient_id}", "{id}")
            try:
                log_event("http", method=request.method, route=route, status=status,
                          duration_ms=round((perf_counter() - start) * 1000, 3))
            finally:
                request_id_context.reset(token)
