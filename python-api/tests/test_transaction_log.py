"""Contratos ASGI sin red ni PostgreSQL: python -m unittest discover -s tests -v."""

import asyncio
import json
import unittest
from unittest.mock import patch
from uuid import UUID, uuid4

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import StreamingResponse

from app import observability
from app.transaction_log import BODY_LIMIT, BodyCapture


async def call_asgi(app, *, path="/patients", method="POST", body=b"", headers=(), chunks=None):
    queue = list(chunks) if chunks is not None else [body]
    sent = []

    async def receive():
        if queue:
            content = queue.pop(0)
            return {"type": "http.request", "body": content, "more_body": bool(queue)}
        await asyncio.Event().wait()

    async def send(message):
        sent.append(message.copy())

    scope = {"type": "http", "asgi": {"version": "3.0", "spec_version": "2.4"},
             "http_version": "1.1", "scheme": "http", "method": method,
             "path": path, "raw_path": path.encode(), "root_path": "", "query_string": b"",
             "headers": [(b"content-type", b"application/json"), *headers],
             "client": ("127.0.0.1", 1000), "server": ("test", 80)}
    await app(scope, receive, send)
    start = next(message for message in sent if message["type"] == "http.response.start")
    response_body = b"".join(message.get("body", b"") for message in sent if message["type"] == "http.response.body")
    return start["status"], dict(start["headers"]), response_body, scope


class TransactionLogTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.rows = []
        self.writer = self.enterContext(patch.object(observability, "write_transaction", side_effect=self.rows.append))
        self.log = self.enterContext(patch.object(observability, "log_event"))
        self.app = FastAPI(telemetry={"tracing": False, "operation_spans": False})
        observability.install_request_logging(self.app)

        @self.app.post("/patients")
        async def echo(body: dict, request: Request):
            return {"echo": body, "execution_id": request.state.execution_id}

        @self.app.get("/patients/{patient_id}")
        async def patient(patient_id: int):
            if patient_id == 500:
                raise RuntimeError("secret-never-in-response-or-log")
            raise HTTPException(404, "Paciente no encontrado")

        @self.app.get("/health")
        async def health():
            return {"status": "ok"}

        @self.app.post("/clinical/stream")
        async def stream(request: Request):
            content = await request.body()

            async def parts():
                for start in range(0, len(content), 12000):
                    yield content[start:start + 12000]

            return StreamingResponse(parts(), media_type="text/plain")

        @self.app.delete("/clinical/empty")
        async def empty():
            return Response(status_code=204)

    async def test_preserves_full_body_and_propagates_execution_uuid(self):
        ident = str(uuid4())
        request_body = json.dumps({"name": "Ana sintética"}, ensure_ascii=False).encode()
        status, headers, body, _ = await call_asgi(self.app, body=request_body,
            headers=[(b"x-execution-id", ident.encode()), (b"x-request-id", b"custom-log-id")])
        self.assertEqual(status, 200)
        self.assertEqual(headers[b"x-execution-id"].decode(), ident)
        self.assertEqual(json.loads(body)["execution_id"], ident)
        row, = self.rows
        self.assertNotIn("execution_id", row)
        self.assertNotIn("request_id", row)
        self.assertIsNone(row["patient_id"])
        self.assertEqual(row["request_body"], request_body.decode())
        self.assertEqual(row["response_body"], body.decode())
        self.assertEqual(row["operation"], "POST /patients")
        self.assertEqual(row["service"], "python")
        self.assertFalse(row["request_truncated"])
        self.assertFalse(row["response_truncated"])
        self.assertIsNone(observability.execution_id_context.get())
        self.assertIsNone(observability.request_id_context.get())

    async def test_invalid_uuid_replaced_and_validation_error_audited(self):
        status, headers, body, _ = await call_asgi(self.app, body=b"broken-json",
            headers=[(b"x-execution-id", b"not-a-uuid")])
        self.assertEqual(status, 422)
        UUID(headers[b"x-execution-id"].decode())
        self.assertEqual(self.rows[0]["request_body"], "broken-json")
        self.assertEqual(self.rows[0]["response_body"], body.decode())
        self.assertEqual(self.rows[0]["http_status"], 422)

    async def test_404_and_normalized_route(self):
        status, _, body, _ = await call_asgi(self.app, path="/patients/12", method="GET")
        self.assertEqual(status, 404)
        self.assertEqual(self.rows[0]["operation"], "GET /patients/{id}")
        self.assertEqual(self.rows[0]["path"], "/patients/12")
        self.assertEqual(self.rows[0]["patient_id"], 12)
        self.assertEqual(self.rows[0]["response_body"], body.decode())

    async def test_unread_body_is_captured_on_unknown_api_route(self):
        status, _, _, _ = await call_asgi(self.app, path="/clinical/absent", body=b'{"note":"report"}')
        self.assertEqual(status, 404)
        self.assertEqual(self.rows[0]["request_body"], '{"note":"report"}')

    async def test_500_returns_and_audits_the_same_generic_body(self):
        status, headers, body, _ = await call_asgi(self.app, path="/patients/500", method="GET")
        self.assertEqual(status, 500)
        self.assertEqual(body, b'{"detail":"Error interno"}')
        self.assertEqual(self.rows[0]["response_body"], body.decode())
        self.assertEqual(self.rows[0]["http_status"], 500)
        self.assertEqual(self.rows[0]["patient_id"], 500)
        UUID(headers[b"x-execution-id"].decode())
        self.assertNotIn("secret-never", repr(self.log.call_args_list))

    async def test_streaming_is_preserved_while_both_captures_are_bounded(self):
        content = b"a" * (BODY_LIMIT + 100000)
        chunks = [content[:20000], content[20000:40000], content[40000:80000], content[80000:]]
        status, _, body, _ = await call_asgi(self.app, path="/clinical/stream", chunks=chunks)
        self.assertEqual(status, 200)
        self.assertEqual(body, content)
        self.assertEqual(len(self.rows[0]["request_body"]), BODY_LIMIT)
        self.assertEqual(len(self.rows[0]["response_body"]), BODY_LIMIT)
        self.assertTrue(self.rows[0]["request_truncated"])
        self.assertTrue(self.rows[0]["response_truncated"])

    async def test_empty_delete_response(self):
        status, _, body, _ = await call_asgi(self.app, path="/clinical/empty", method="DELETE")
        self.assertEqual((status, body), (204, b""))
        self.assertEqual(self.rows[0]["response_body"], "")

    async def test_health_does_not_write_transaction(self):
        status, headers, _, _ = await call_asgi(self.app, path="/health", method="GET")
        self.assertEqual(status, 200)
        self.assertIn(b"x-execution-id", headers)
        self.assertEqual(self.rows, [])

    async def test_audit_failure_does_not_rewrite_successful_business_response(self):
        self.writer.side_effect = RuntimeError("secret-body-or-sql-parameters")
        status, _, body, _ = await call_asgi(self.app, body=b'{"name":"Demo"}')
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body)["echo"], {"name": "Demo"})
        errors = [call for call in self.log.call_args_list if call.args == ("transaction_log",)]
        self.assertEqual(len(errors), 1)
        self.assertEqual(errors[0].kwargs, {"status": "error", "error_type": "RuntimeError"})
        self.assertNotIn("secret-body", repr(self.log.call_args_list))

    async def test_parallel_requests_do_not_mix_execution_ids(self):
        identifiers = [str(uuid4()), str(uuid4())]
        responses = await asyncio.gather(*(call_asgi(self.app, body=b"{}",
            headers=[(b"x-execution-id", ident.encode())]) for ident in identifiers))
        self.assertEqual(len(self.rows), len(identifiers))
        self.assertTrue(all("execution_id" not in row and "request_id" not in row for row in self.rows))
        for response, ident in zip(responses, identifiers):
            self.assertEqual(json.loads(response[2])["execution_id"], ident)
            self.assertEqual(response[1][b"x-execution-id"].decode(), ident)
        self.assertIsNone(observability.execution_id_context.get())

    async def test_headers_are_not_persisted(self):
        await call_asgi(self.app, body=b"{}", headers=[(b"authorization", b"Bearer secret-token")])
        self.assertNotIn("secret-token", repr(self.rows))

    async def test_same_middleware_order_as_main_keeps_metrics_and_stream(self):
        from app.metrics import install_metrics

        app = FastAPI(telemetry={"tracing": False, "operation_spans": False})
        install_metrics(app)
        observability.install_request_logging(app)

        @app.post("/clinical/middleware-check")
        async def stream(request: Request):
            content = await request.body()
            return StreamingResponse(iter([content[:3], content[3:]]))

        status, _, body, _ = await call_asgi(app, path="/clinical/middleware-check", chunks=[b"first", b"second"])
        self.assertEqual((status, body), (200, b"firstsecond"))
        self.assertEqual(self.rows[0]["request_body"], "firstsecond")
        self.assertEqual(self.rows[0]["response_body"], "firstsecond")
        _, _, metrics, _ = await call_asgi(app, path="/metrics", method="GET")
        self.assertIn(b'route="/clinical/middleware-check",status="200"} 1.0', metrics)
        self.assertEqual(len(self.rows), 1)

    def test_nul_is_visible_without_breaking_postgres_text(self):
        capture = BodyCapture()
        capture.add(b"before\x00after")
        self.assertEqual(capture.text(), "before\\u0000after")


if __name__ == "__main__":
    unittest.main()
