"""Identificador de petición y eventos JSON para seguir una consulta."""

import json
import logging
import re
import sys
from collections import deque
from contextvars import ContextVar
from datetime import datetime, timezone
from time import perf_counter
from uuid import UUID, uuid4

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool
from starlette.datastructures import Headers, MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.transaction_log import BodyCapture, write_transaction

request_id_context: ContextVar[str | None] = ContextVar("request_id", default=None)
execution_id_context: ContextVar[str | None] = ContextVar("execution_id", default=None)
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
        "event": event, "request_id": request_id_context.get(),
        "execution_id": execution_id_context.get(), **fields,
    }, ensure_ascii=False))


def install_request_logging(app: FastAPI) -> None:
    @app.exception_handler(Exception)
    async def internal_error(request: Request, error: Exception):
        # Starlette construye el 500 fuera del middleware: conserva también allí el id.
        return JSONResponse(status_code=500, content={"detail": "Error interno"},
                            headers={"X-Request-ID": request.state.request_id,
                                     "X-Execution-ID": request.state.execution_id})

    app.add_middleware(RequestLoggingMiddleware)


def is_audited_path(path: str) -> bool:
    # Las sondas y los assets no son transacciones de la aplicación.
    return any(path == prefix or path.startswith(prefix + "/")
               for prefix in ("/patients", "/chat", "/clinical"))


class RequestLoggingMiddleware:
    """Captura acotada sin consumir ni reconstruir la respuesta de streaming.

    SQL recibe las transacciones API; stdout conserva además las métricas y sondas.
    Si SQL falla, se emite transaction_log/error sin afirmar que una escritura de
    negocio ya realizada se haya deshecho. No se guardan headers ni variables de entorno.
    """

    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = Headers(scope=scope)
        supplied = headers.get("X-Request-ID", "")
        request_id = supplied if re.fullmatch(r"[A-Za-z0-9._:-]{1,128}", supplied) else str(uuid4())
        try:
            execution_id = str(UUID(headers.get("X-Execution-ID", "")))
        except ValueError:
            execution_id = str(uuid4())
        scope.setdefault("state", {}).update(request_id=request_id, execution_id=execution_id)
        token = request_id_context.set(request_id)
        execution_token = execution_id_context.set(execution_id)
        start = perf_counter()
        audited = is_audited_path(scope["path"])
        incoming, outgoing = BodyCapture(), BodyCapture()
        buffered: deque[Message] = deque()
        status = 500
        response_started = False
        response_completed = False
        audit_attempted = False

        async def record_transaction():
            nonlocal audit_attempted
            if not audited or audit_attempted:
                return
            audit_attempted = True
            route = getattr(scope.get("route"), "path", "unmatched").replace("{patient_id}", "{id}")
            try:
                await run_in_threadpool(write_transaction, {
                    "execution_id": UUID(execution_id), "request_id": request_id, "service": "python",
                    "operation": f"{scope['method']} {route}", "method": scope["method"],
                    "path": scope["path"], "http_status": status,
                    "request_body": incoming.text(), "response_body": outgoing.text(),
                    "request_truncated": incoming.truncated, "response_truncated": outgoing.truncated,
                    "duration_ms": round((perf_counter() - start) * 1000, 3),
                })
            except Exception as error:
                # No incluir SQL/parametros: pueden contener cuerpos o credenciales.
                log_event("transaction_log", status="error", error_type=type(error).__name__)

        async def capture_receive():
            if buffered:
                return buffered.popleft()
            message = await receive()
            if audited and message["type"] == "http.request":
                incoming.add(message.get("body", b""))
            return message

        async def capture_send(message: Message):
            nonlocal status, response_started, response_completed
            if message["type"] == "http.response.start":
                response_started = True
                status = message["status"]
                response_headers = MutableHeaders(scope=message)
                response_headers["X-Request-ID"] = request_id
                response_headers["X-Execution-ID"] = execution_id
            elif message["type"] == "http.response.body":
                if audited:
                    outgoing.add(message.get("body", b""))
                if not message.get("more_body", False):
                    response_completed = True
                    # Antes del último chunk: al terminar el cliente ya puede consultar la fila.
                    await record_transaction()
            await send(message)

        try:
            if audited:
                # Captura también el body de rutas que lo rechazan sin leerlo (404/405).
                # Sólo anticipa un prefijo; el resto sigue fluyendo sin buffer completo.
                while True:
                    message = await receive()
                    buffered.append(message)
                    if message["type"] != "http.request":
                        break
                    incoming.add(message.get("body", b""))
                    if not message.get("more_body", False):
                        break
                    if incoming.truncated:
                        break
            try:
                await self.app(scope, capture_receive, capture_send)
            except Exception as error:
                log_event("http_error", error_type=type(error).__name__)
                if response_started:
                    outgoing.truncated = not response_completed or outgoing.truncated
                    raise
                # Conserva exactamente el 500 genérico en SQL y en la respuesta HTTP.
                await JSONResponse(status_code=500, content={"detail": "Error interno"})(
                    scope, capture_receive, capture_send)
        finally:
            route = getattr(scope.get("route"), "path", "unmatched").replace("{patient_id}", "{id}")
            try:
                await record_transaction()
                log_event("http", method=scope["method"], route=route, status=status,
                          duration_ms=round((perf_counter() - start) * 1000, 3))
            finally:
                request_id_context.reset(token)
                execution_id_context.reset(execution_token)
