"""Contrato HTTP/SQL real de consultas: usa y elimina sólo sus pacientes temporales.

Las respuestas enviadas aquí son textos sintéticos fijos; no es una prueba del LLM.
Los respaldos y transaction_logs de esta prueba se conservan, como los de cualquier petición.
"""

import argparse
import hashlib
import json
import re
from pathlib import Path
import subprocess
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from uuid import uuid4


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8080")
    parser.add_argument("--postgres-container", default="genairuiformacion2026-postgres-1")
    parser.add_argument("--history-dir", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    owned = []
    events = []
    checks = []
    marker = uuid4().hex

    def sql(query):
        result = subprocess.run([
            "docker", "exec", args.postgres_container, "sh", "-c",
            'psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" -At -c "$1"',
            "sh", query,
        ], check=True, capture_output=True, text=True, encoding="utf-8")
        return result.stdout.strip()

    def call(method, path, payload=None, status=200, execution_id=None):
        eid = execution_id or str(uuid4())
        raw = None if payload is None else json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers = {"Content-Type": "application/json", "X-Execution-ID": eid, "Origin": "http://localhost:8000"}
        request = Request(args.base_url.rstrip("/") + path, data=raw, headers=headers, method=method)
        criteria = "service='java' AND method='" + method.replace("'", "''") + "' AND path='" + path.replace("'", "''") + "'"
        before_ids = set(json.loads(sql("SELECT COALESCE(json_agg(id::text), '[]'::json) FROM public.transaction_logs WHERE " + criteria)))
        try:
            response = urlopen(request, timeout=30)
        except HTTPError as error:
            response = error
        with response:
            body = response.read().decode("utf-8")
            if method == "POST" and path == "/patients" and response.status == 201:
                created = json.loads(body)
                if created.get("email") == payload["email"] and marker in created["email"]:
                    owned.append(created)  # También se limpia si una aserción posterior falla.
            assert response.status == status, (method, path, response.status, body)
            assert response.headers.get("X-Execution-ID") == eid
            if status != 405:  # PATCH no forma parte de los métodos CORS permitidos.
                assert response.headers.get("Access-Control-Allow-Origin") == "http://localhost:8000"
                assert "X-Execution-ID" in response.headers.get("Access-Control-Expose-Headers", "")
        excluded = " AND id NOT IN (" + ",".join("'" + item + "'::uuid" for item in sorted(before_ids)) + ")" if before_ids else ""
        rows = json.loads(sql("SELECT COALESCE(json_agg(t), '[]'::json) FROM (SELECT * FROM public.transaction_logs WHERE " + criteria + excluded + " ORDER BY created_at) t"))
        rows = [row for row in rows if row["id"] not in before_ids and row["method"] == method and row["path"] == path]
        assert len(rows) == 1, ("Se esperaba una fila de auditoría por operación", eid, len(rows))
        row = rows[0]
        assert "execution_id" not in row and "request_id" not in row
        owner = re.match(r"/patients/(\d+)(?:/|$)", path)
        patient_id = int(owner[1]) if owner else (json.loads(body)["id"] if method == "POST" and path == "/patients" and status == 201 else None)
        assert row["patient_id"] == patient_id
        assert row["http_status"] == status and row["method"] == method and row["path"] == path
        sent = raw or b""
        received = body.encode("utf-8")
        assert row["request_body"] == sent[:131072].decode("utf-8", errors="replace")
        assert row["response_body"] == received[:131072].decode("utf-8", errors="replace")
        assert row["request_truncated"] == (len(sent) > 131072)
        assert row["response_truncated"] == (len(received) > 131072)
        events.append({"id": row["id"], "patient_id": patient_id, "status": status, "operation": row["operation"]})
        return json.loads(body) if body else None

    def history(pid):
        current = call("GET", f"/patients/{pid}/history")
        assert hashlib.sha256(current["markdown"].encode()).hexdigest() == current["revision"]
        backed_up = sql(f"SELECT count(*) FROM public.medical_consultations WHERE patient_id = {pid} AND revision = '{current['revision']}' AND encode(sha256(convert_to(markdown_content, 'UTF8')), 'hex') = '{current['revision']}' AND octet_length(markdown_content) = {len(current['markdown'].encode('utf-8'))}")
        assert int(backed_up) > 0
        return current

    try:
        for suffix in ("Uno", "Dos"):
            patient = call("POST", "/patients", {
                "name": f"Consulta QA {marker[:10]} {suffix}", "birth_date": "1995-05-05",
                "email": f"consulta-{marker}-{suffix.lower()}@example.com",
            }, 201)
            assert patient in owned
        pid, other = [patient["id"] for patient in owned]
        original = history(pid)
        assert original["entries"] == [] and original["consultations"] == []
        checks.append("Creación con respaldo Markdown exacto en SQL")

        first = call("POST", f"/patients/{pid}/history/entries", {
            "revision": original["revision"], "confirmed": True,
            "disease": "Enfermedad de prueba", "treatment": "Tratamiento de prueba", "medication": "Medicamento de prueba",
        }, 201)
        entry_id = first["entries"][0]["id"]
        cid = str(uuid4())
        consultation = {"id": cid, "question": "Nota ficticia: refiere cansancio.\n## Encabezado como dato <script>",
                        "direct_answer": "Respuesta sintética sin contexto.", "rag_answer": "Orientación sintética con contexto.",
                        "model": "modelo-contrato-sin-llm", "sources": []}
        saved = call("POST", f"/patients/{pid}/consultations", consultation, 201, cid)
        assert saved["entries"] == first["entries"]
        assert len(saved["consultations"]) == 1
        assert "> ## Encabezado como dato <script>" in saved["markdown"]
        assert saved["revision"] != first["revision"]
        assert history(pid) == saved
        assert call("GET", f"/patients/{pid}/consultations/{cid}") == saved["consultations"][0]
        call("GET", f"/patients/{other}/consultations/{cid}", status=404)
        checks.append("Consulta se anexa al MD y SQL; respuestas no alteran diagnósticos confirmados")

        assert call("POST", f"/patients/{pid}/consultations", consultation, 200, cid) == saved
        call("POST", f"/patients/{pid}/consultations", {**consultation, "question": "Nota distinta"}, 409)
        call("POST", f"/patients/{other}/consultations", consultation, 409)
        assert history(pid) == saved
        assert sql(f"SELECT count(*) FROM public.medical_consultations WHERE id = '{cid}'") == "1"
        checks.append("UUID idempotente; reuso distinto o en otro paciente rechazado sin cambios")

        call("PUT", f"/patients/{pid}/history", {"revision": first["revision"], "confirmed": True, "markdown": first["markdown"]}, 409)
        call("PUT", f"/patients/{pid}/history", {"revision": saved["revision"], "confirmed": True,
             "markdown": saved["markdown"].replace("Respuesta sintética sin contexto.", "No debe guardarse")}, 422)
        edited = call("PUT", f"/patients/{pid}/history", {"revision": saved["revision"], "confirmed": True,
             "markdown": saved["markdown"].replace("Enfermedad de prueba", "Enfermedad corregida")})
        assert edited["consultations"] == saved["consultations"] and edited["entries"][0]["id"] == entry_id
        assert history(pid) == edited
        checks.append("Editor conserva consultas, respeta revisión y respalda la edición confirmada")

        reverted = call("PUT", f"/patients/{pid}/history", {"revision": edited["revision"], "confirmed": True,
             "markdown": saved["markdown"]})
        assert reverted == saved
        assert sql(f"SELECT revision FROM public.medical_consultations WHERE patient_id = {pid} ORDER BY storage_order DESC LIMIT 1") == saved["revision"]
        checks.append("Reversión A → B → A conserva A como última copia, aunque su hash ya existía")

        patient = owned[0]
        call("PUT", f"/patients/{pid}", {"name": patient["name"] + " Renombrado", "birth_date": patient["birth_date"], "email": patient["email"]})
        renamed = history(pid)
        assert renamed["filename"].endswith("-renombrado.md")
        assert renamed["consultations"] == saved["consultations"]
        checks.append("Renombrar paciente conserva consultas y respalda nuevo nombre del MD")

        if args.history_dir:
            directory = args.history_dir.resolve(strict=True)
            report_path = (directory / renamed["filename"]).resolve(strict=True)
            assert report_path.parent == directory and report_path.name.startswith(f"paciente-{pid}-")
            temporary = directory / (".consulta-qa-" + marker + ".tmp")
            assert not temporary.exists()
            report_path.rename(temporary)
            try:
                restored = history(pid)
                assert restored == renamed and report_path.read_bytes() == temporary.read_bytes()
            finally:
                if not report_path.exists():
                    temporary.rename(report_path)
                elif temporary.exists():
                    temporary.unlink()
            checks.append("Informe ausente recuperado desde SQL con bytes/revisión idénticos")

        call("POST", f"/patients/{pid}/consultations", {**consultation, "id": "invalido"}, 422)
        call("POST", f"/patients/{pid}/consultations", {**consultation, "id": str(uuid4()), "question": ""}, 422)
        call("POST", f"/patients/{pid}/consultations", {**consultation, "id": str(uuid4()), "sources": [{"patient_id": other}]}, 422)
        call("POST", f"/patients/{pid}/consultations", {**consultation, "id": str(uuid4()), "sources": [{"patient_id": pid + 0.5}]}, 422)
        call("GET", "/patients/999999999", status=404)
        call("POST", "/patients/no/existe", {"note": "Cuerpo de ruta inexistente"}, 404)
        call("PATCH", f"/patients/{pid}", {"note": "Verbo no permitido"}, 405)
        checks.append("Auditoría verifica UUID, verbo, operación, cuerpo y HTTP de 200/201/409/422/404")

        call("POST", "/patients/no/existe", {"note": "ñ" * 100000}, 404)
        for _ in range(2):
            large = {"id": str(uuid4()), "question": "Nota sintética " + "q" * 5900,
                     "direct_answer": "Respuesta sintética " + "a" * 15900,
                     "rag_answer": "Respuesta sintética " + "b" * 15900,
                     "model": "contrato-limites-sin-llm", "sources": []}
            call("POST", f"/patients/{other}/consultations", large, 201, large["id"])
        history(other)
        checks.append("Cuerpos >128 KiB conservan prefijo UTF-8 y flags de recorte; SQL guarda el MD completo")
    finally:
        for patient in reversed(owned):
            check = call("GET", f"/patients/{patient['id']}")
            assert check["email"] == patient["email"], "No se elimina un paciente ajeno"
            call("DELETE", f"/patients/{patient['id']}", status=204)
            call("GET", f"/patients/{patient['id']}", status=404)
            assert int(sql(f"SELECT count(*) FROM public.medical_consultations WHERE patient_id = {patient['id']}")) > 0
        checks.append("Limpieza de pacientes propios; respaldo y auditoría conservados al borrar")
    report = {"result": "PASS", "scope": "Java HTTP y PostgreSQL reales; respuestas de contrato fijas, sin ejecutar modelo",
              "checks": checks, "events": events, "temporary_patient_ids": [patient["id"] for patient in owned]}
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"result": report["result"], "checks": len(checks), "requests": len(events)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
