"""Integración Python/SQL/MD: crea y elimina únicamente sus dos pacientes temporales.

Get-Content -Raw scripts/verificar_unificacion_python.py | docker compose exec -T python-api python -
No requiere Java, Ollama ni Qdrant; también sirve en S1.
"""

import hashlib
import json
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from uuid import UUID, uuid4

from sqlalchemy import text
from app.clinical_store import DIRECTORY
from app.db import engine

BASE = "http://127.0.0.1:8000"
run_id = str(uuid4())
owned = []
results = []


def call(method, path, expected, body=None):
    payload = json.dumps(body, ensure_ascii=False).encode() if body is not None else None
    request = Request(BASE + path, data=payload, method=method, headers={"Content-Type": "application/json"})
    try:
        response = urlopen(request, timeout=30)
    except HTTPError as error:
        response = error
    with response:
        raw, status = response.read(), response.status
    parsed = json.loads(raw) if raw else None
    if method == "POST" and path == "/patients" and status == 201:
        assert run_id in parsed["email"]
        owned.append(parsed["id"])
    assert status == expected, (method, path, status, expected, parsed)
    results.append({"method": method, "path": path, "status": status})
    return parsed


def verify_projection(patient_id, expected):
    paths = list(DIRECTORY.glob(f"paciente-{patient_id}-*.md"))
    assert len(paths) == 1
    raw = paths[0].read_bytes()
    with engine.connect() as connection:
        rows = connection.execute(text("SELECT id,patient_id,disease,treatment,medication "
                                       "FROM public.patient_diseases WHERE patient_id=:id"), {"id": patient_id}).mappings().all()
        latest = connection.execute(text("SELECT filename,markdown_content,revision FROM public.medical_consultations "
                                         "WHERE patient_id=:id ORDER BY storage_order DESC LIMIT 1"), {"id": patient_id}).mappings().one()
    normalized = [{**row, "id": str(row["id"])} for row in rows]
    assert sorted(normalized, key=lambda row: row["id"]) == sorted(expected, key=lambda row: row["id"])
    assert latest["filename"] == paths[0].name
    assert latest["markdown_content"].encode() == raw
    assert latest["revision"] == hashlib.sha256(raw).hexdigest()
    for entry in expected:
        assert f"## Registro {entry['id']}" in raw.decode()
    return paths[0]


before = call("GET", "/patients", 200)
try:
    patient = call("POST", "/patients", 201, {"name": "Prueba unificación Python", "birth_date": "1995-01-01",
                                              "email": f"unificacion-{run_id}@example.com"})
    patient_id = patient["id"]
    assert patient_id not in {row["id"] for row in before}
    initial_path = verify_projection(patient_id, [])
    assert call("GET", f"/patients/{patient_id}/diseases", 200) == []
    entry = call("POST", f"/patients/{patient_id}/diseases", 201,
                 {"disease": "Rinitis alérgica", "treatment": "Evitar polen", "medication": "Cetirizina"})
    UUID(entry["id"])
    verify_projection(patient_id, [entry])
    assert call("GET", f"/patients/{patient_id}/diseases/{entry['id']}", 200) == entry
    other = call("POST", "/patients", 201, {"name": "Otro temporal Python", "birth_date": "1995-01-01",
                                            "email": f"otro-{run_id}@example.com"})
    other_path = f"/patients/{other['id']}/diseases/{entry['id']}"
    call("GET", other_path, 404)
    call("PUT", other_path, 404, {"disease": "No cambiar", "treatment": "", "medication": ""})
    call("DELETE", other_path, 404)
    call("POST", f"/patients/{patient_id}/diseases", 422, {"disease": "", "treatment": "", "medication": ""})
    updated = call("PUT", f"/patients/{patient_id}/diseases/{entry['id']}", 200,
                   {"disease": "Rinitis alérgica", "treatment": "Lavado nasal", "medication": ""})
    assert updated["id"] == entry["id"]
    verify_projection(patient_id, [updated])
    call("PUT", f"/patients/{patient_id}", 200, {**patient, "name": "Paciente renombrado Python"})
    renamed_path = verify_projection(patient_id, [updated])
    assert renamed_path != initial_path and not initial_path.exists()
    call("DELETE", f"/patients/{patient_id}/diseases/{entry['id']}", 204)
    verify_projection(patient_id, [])
    call("GET", f"/patients/{patient_id}/diseases/{entry['id']}", 404)
    call("POST", f"/patients/{patient_id}/diseases", 201, {"disease": "Registro para cascada", "treatment": "", "medication": ""})
    call("DELETE", f"/patients/{patient_id}", 204)
    assert not renamed_path.exists()
    with engine.connect() as connection:
        assert connection.execute(text("SELECT count(*) FROM public.patient_diseases WHERE patient_id=:id"), {"id": patient_id}).scalar_one() == 0
        assert connection.execute(text("SELECT kind FROM public.medical_consultations WHERE patient_id=:id ORDER BY storage_order DESC LIMIT 1"), {"id": patient_id}).scalar_one() == "deleted"
        columns = connection.execute(text("SELECT column_name FROM information_schema.columns WHERE table_schema='public' AND table_name='transaction_logs' AND data_type='uuid'")).scalars().all()
        assert columns == ["id"]
        assert connection.execute(text("SELECT count(*) FROM public.transaction_logs WHERE patient_id=:id AND service='python' AND method='DELETE' AND http_status=204"), {"id": patient_id}).scalar_one() >= 2
finally:
    for patient_id in owned:
        request = Request(BASE + f"/patients/{patient_id}", method="DELETE")
        try:
            with urlopen(request, timeout=30) as response:
                assert response.status == 204
        except HTTPError as error:
            assert error.code == 404

assert call("GET", "/patients", 200) == before
assert all(not list(DIRECTORY.glob(f"paciente-{patient_id}-*.md")) for patient_id in owned)
print(json.dumps({"result": "PASS", "run_id": run_id, "requests": results, "count": len(results),
                  "temporary_patients_deleted": owned, "original_patients_preserved": True,
                  "markdown_sql_uuid_cascade_and_audit": True}, ensure_ascii=False, indent=2))
