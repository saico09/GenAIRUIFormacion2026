"""Prueba la API desplegada y sus filas SQL; sólo crea/borra un paciente temporal propio.

Desde codigo (PowerShell):
Get-Content -Raw scripts/verificar_auditoria_python.py | docker compose exec -T python-api python -
"""

import hashlib
import json
import time
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from uuid import UUID, uuid4

from sqlalchemy import text

from app.db import engine


BASE = "http://127.0.0.1:8000"
RUN_ID = str(uuid4())
EMAIL = f"audit-python-{RUN_ID}@example.com"
report = {"run_id": RUN_ID, "result": "RUNNING", "requests": [], "original_patients_preserved": False}
temporary_id = None


def digest(value):
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def call(method, path, expected, body=None, *, raw=None, execution=None):
    global temporary_id
    execution = execution or str(uuid4())
    payload = raw if raw is not None else (json.dumps(body, ensure_ascii=False).encode() if body is not None else None)
    headers = {"Content-Type": "application/json", "X-Execution-ID": execution,
               "X-Request-ID": "audit-python-" + str(uuid4())}
    request = Request(BASE + path, data=payload, headers=headers, method=method)
    try:
        response = urlopen(request, timeout=30)
    except HTTPError as error:
        response = error
    with response:
        status, actual_headers, actual_body = response.status, dict(response.headers), response.read()
    # Conservar el ID antes de verificar SQL permite limpiar incluso si falla la auditoría.
    if method == "POST" and path == "/patients" and status == 201:
        candidate = json.loads(actual_body)
        if candidate.get("email") == EMAIL and isinstance(candidate.get("id"), int):
            temporary_id = candidate["id"]
    response_execution = next(value for key, value in actual_headers.items() if key.lower() == "x-execution-id")
    assert response_execution == execution, ("execution_header", path, response_execution, execution)
    UUID(response_execution)
    deadline = time.monotonic() + 5
    while True:
        with engine.connect() as connection:
            rows = connection.execute(text("""
                SELECT id, execution_id, request_id, service, operation, method, path, http_status,
                       request_body, response_body, request_truncated, response_truncated, duration_ms
                FROM public.transaction_logs WHERE execution_id = :execution AND service = 'python'
                """), {"execution": UUID(execution)}).mappings().all()
        if rows or time.monotonic() >= deadline:
            break
        time.sleep(0.1)
    assert len(rows) == 1, ("one_transaction", path, len(rows))
    row = rows[0]
    UUID(str(row["id"]))
    assert str(row["execution_id"]) == execution
    assert row["request_id"] == headers["X-Request-ID"]
    assert row["service"] == "python"
    assert row["method"] == method and row["path"] == path
    assert row["http_status"] == status == expected, ("http_status", path, row["http_status"], status, expected)
    assert row["request_body"] == (payload or b"").decode(), ("request_body", path)
    assert row["response_body"] == actual_body.decode(), ("response_body", path)
    assert not row["request_truncated"] and not row["response_truncated"]
    assert row["duration_ms"] >= 0
    if path.startswith("/patients/") and path.rsplit("/", 1)[1].isdigit():
        assert row["operation"] == f"{method} /patients/{{id}}", ("normalized_route", row["operation"])
    report["requests"].append({
        "method": method, "path": path, "status": status, "execution_id": execution,
        "transaction_id": str(row["id"]), "operation": row["operation"],
        "body_match": True, "uuid_match": True, "truncated": False,
    })
    return json.loads(actual_body) if actual_body else None


try:
    before = call("GET", "/patients", 200)
    by_id = {item["id"]: item for item in before}
    report["original_patient_ids"] = sorted(by_id)
    report["original_patients_sha256"] = digest(before)
    created = call("POST", "/patients", 201, {
        "name": "Prueba auditoria Python", "birth_date": "1995-05-05", "email": EMAIL,
    })
    temporary_id = created["id"]
    assert temporary_id not in by_id and created["email"] == EMAIL
    current = call("GET", f"/patients/{temporary_id}", 200)
    assert current == created
    call("PUT", f"/patients/{temporary_id}", 422, {
        "name": "No debe guardarse", "birth_date": "1995-05-05", "email": "sin-arroba",
    })
    assert call("GET", f"/patients/{temporary_id}", 200) == created
    updated = call("PUT", f"/patients/{temporary_id}", 200, {
        "name": "Prueba auditoria editada", "birth_date": "1995-05-05", "email": EMAIL,
    })
    assert updated["id"] == temporary_id and updated["email"] == EMAIL
    assert updated["name"] == "Prueba auditoria editada"
    call("GET", "/patients/2147483647", 404)
    call("POST", f"/clinical/audit-absent-{RUN_ID}", 404, {"note": "raw body preserved on 404"})
    call("PATCH", "/patients", 405, {"note": "raw body preserved on 405"})
    call("POST", "/patients", 422, raw=b'{"invalid":')
    assert call("GET", f"/patients/{temporary_id}", 200)["email"] == EMAIL
    deleted_id = temporary_id
    call("DELETE", f"/patients/{temporary_id}", 204)
    temporary_id = None
    call("GET", f"/patients/{deleted_id}", 404)
    after = call("GET", "/patients", 200)
    after_by_id = {item["id"]: item for item in after}
    assert all(after_by_id.get(identifier) == value for identifier, value in by_id.items())
    assert all(item["email"] != EMAIL for item in after)
    report["original_patients_preserved"] = True
    report["result"] = "PASS"
    report["temporary_patient_deleted"] = deleted_id
except Exception as error:
    report["result"] = "FAIL"
    report["error"] = {"type": type(error).__name__, "message": str(error)}
    raise
finally:
    if temporary_id is not None:
        try:
            # La limpieza no depende de que la tabla de auditoría esté disponible.
            with urlopen(BASE + f"/patients/{temporary_id}", timeout=15) as response:
                owned = json.load(response)
            if owned["email"] == EMAIL:
                with urlopen(Request(BASE + f"/patients/{temporary_id}", method="DELETE"), timeout=15) as response:
                    assert response.status == 204
                report["cleanup_deleted_id"] = temporary_id
            else:
                report["cleanup_error"] = "El ID no coincide con el email propio; no se borro"
        except Exception as cleanup_error:
            report["cleanup_error"] = str(cleanup_error)
    print(json.dumps(report, ensure_ascii=False, indent=2))
