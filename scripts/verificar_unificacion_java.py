"""Regresión real cruzada, con dos pacientes temporales y sin llamar al LLM.

python scripts/verificar_unificacion_java.py --postgres-container genai-postgres --output resultado.json
El caso de rollback instala un trigger SQL temporal limitado a su paciente de prueba.
Siempre retira el trigger y elimina los pacientes; conserva las filas históricas de auditoría.
"""

from __future__ import annotations

import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import subprocess
import time
import urllib.error
import urllib.request
from uuid import uuid4


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--python", default="http://127.0.0.1:8000")
    parser.add_argument("--java", default="http://127.0.0.1:8080")
    parser.add_argument("--postgres-container", required=True)
    parser.add_argument("--history-dir", type=Path, default=Path(__file__).resolve().parents[1] / "datos/historias")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    bases = {"python": args.python.rstrip("/"), "java": args.java.rstrip("/")}
    token = uuid4().hex
    created: list[int] = []
    calls: list[dict] = []
    checks: list[str] = []
    trigger = "verify_clinical_" + token
    trigger_installed = False
    report = {"started_at": datetime.now(timezone.utc).isoformat(), "run": token, "checks": checks}

    def sql(statement: str):
        result = subprocess.run(
            ["docker", "exec", "-i", args.postgres_container, "sh", "-c",
             'psql -X -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" -At'],
            input=statement, text=True, encoding="utf-8", capture_output=True, check=True,
        )
        return result.stdout.strip()

    def query(statement: str):
        return json.loads(sql(f"SELECT COALESCE(json_agg(t), '[]'::json) FROM ({statement}) t;"))

    def http(service: str, method: str, path: str, body=None, expected=200):
        data = None if body is None else json.dumps(body, ensure_ascii=False).encode("utf-8")
        request = urllib.request.Request(bases[service] + path, data=data, method=method,
                                         headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(request, timeout=40) as response:
                status, raw = response.status, response.read()
        except urllib.error.HTTPError as error:
            status, raw = error.code, error.read()
        try:
            result = json.loads(raw) if raw else None
        except ValueError:
            result = raw.decode("utf-8")
        match = re.match(r"/patients/(\d+)", path)
        patient_id = int(match[1]) if match else (
            result.get("id") if method == "POST" and path == "/patients" and isinstance(result, dict) else None
        )
        calls.append({"service": service, "method": method, "path": path, "http_status": status, "patient_id": patient_id})
        assert status == expected, (service, method, path, status, result)
        return result

    def md_files(patient_id: int):
        return list(args.history_dir.glob(f"paciente-{patient_id}-*.md"))

    def aligned(patient_id: int):
        history = http("java", "GET", f"/patients/{patient_id}/history")
        files = md_files(patient_id)
        assert len(files) == 1
        assert files[0].read_bytes().decode("utf-8") == history["markdown"]
        latest = query(f"SELECT markdown_content, filename, revision FROM public.medical_consultations WHERE patient_id={patient_id} ORDER BY storage_order DESC LIMIT 1")[0]
        assert latest == {"markdown_content": history["markdown"], "filename": history["filename"], "revision": history["revision"]}
        rows = query(f"SELECT id::text, disease, treatment, medication FROM public.patient_diseases WHERE patient_id={patient_id} ORDER BY id")
        assert rows == sorted(history["entries"], key=lambda item: item["id"])
        return history

    try:
        for service in ("python", "java"):
            patient = http(service, "POST", "/patients", {
                "name": f"Prueba unificación {service} {token[:8]}", "birth_date": "1990-01-01",
                "email": f"{service}-{token}@example.com",
            }, 201)
            created.append(patient["id"])
            # Se comprueba antes de GET history: la creación debe escribir el MD por sí misma.
            assert len(md_files(patient["id"])) == 1, "POST no creó automáticamente el Markdown"
            for reader in bases:
                assert http(reader, "GET", f"/patients/{patient['id']}") == patient
            aligned(patient["id"])
        patient_id, other_id = created
        checks.append("Ambas APIs crean el mismo paciente compartido y su MD/SQL automáticamente")

        first = http("java", "POST", f"/patients/{patient_id}/diseases", {
            "disease": "Rinitis alérgica ficticia", "treatment": "Control del desencadenante de prueba", "medication": "Cetirizina"
        }, 201)
        assert first["patient_id"] == patient_id
        assert http("python", "GET", f"/patients/{patient_id}/diseases/{first['id']}") == first
        changed = {"disease": "Rinitis alérgica ficticia", "treatment": "Plan actualizado de prueba", "medication": ""}
        updated = http("python", "PUT", f"/patients/{patient_id}/diseases/{first['id']}", changed)
        assert updated == {"id": first["id"], "patient_id": patient_id, **changed}
        assert http("java", "GET", f"/patients/{patient_id}/diseases/{first['id']}") == updated
        for service in bases:
            for method in ("GET", "PUT", "DELETE"):
                http(service, method, f"/patients/{other_id}/diseases/{first['id']}", changed if method == "PUT" else None, 404)
            for invalid in ({"disease": "", "treatment": "", "medication": ""},
                            {"disease": 123, "treatment": "", "medication": ""},
                            {"disease": "## Encabezado", "treatment": "", "medication": ""},
                            {"disease": "x" * 2001, "treatment": "", "medication": ""}):
                http(service, "POST", f"/patients/{patient_id}/diseases", invalid, 422)
        aligned(patient_id)
        checks.append("CRUD cruzado conserva UUID; valida propietario, campos y límites")

        consultation_id = str(uuid4())
        consultation = {"id": consultation_id, "question": "Nota ficticia de regresión " + token,
                        "direct_answer": "Respuesta fija de prueba sin diagnóstico.",
                        "rag_answer": "Respuesta fija basada en el registro de prueba.",
                        "model": "fixture-sin-LLM", "sources": []}
        saved = http("java", "POST", f"/patients/{patient_id}/consultations", consultation, 201)
        assert http("java", "POST", f"/patients/{patient_id}/consultations", consultation) == saved
        journal_before = saved["markdown"].split("\n## Consultas registradas\n", 1)[1]

        def add(index: int):
            return http("java" if index % 2 else "python", "POST", f"/patients/{patient_id}/diseases", {
                "disease": f"Registro concurrente {index}", "treatment": "Plan de prueba", "medication": ""
            }, 201)

        with ThreadPoolExecutor(max_workers=10) as workers:
            concurrent = list(workers.map(add, range(10)))
        history = aligned(patient_id)
        assert len(history["entries"]) == 11
        assert {item["id"] for item in concurrent} <= {item["id"] for item in history["entries"]}
        assert history["markdown"].split("\n## Consultas registradas\n", 1)[1] == journal_before
        checks.append("Diez escrituras concurrentes Java/Python sin pérdida; diario y reintento conservados")

        rename = {"name": "Paciente renombrado " + token[:8], "birth_date": "1990-01-01", "email": token + "@example.com"}
        for service in bases:
            rename["name"] = "Renombrado " + service + " " + token[:8]
            http(service, "PUT", f"/patients/{patient_id}", rename)
            history = aligned(patient_id)
            assert rename["name"] in history["markdown"]
            assert history["markdown"].split("\n## Consultas registradas\n", 1)[1] == journal_before
        checks.append("Renombrar por ambas APIs conserva un solo archivo, UUID y diario")

        # El fallo se dispara en COMMIT, después de escribir el archivo; sólo afecta este paciente.
        sql(f"""
CREATE FUNCTION public.{trigger}() RETURNS trigger LANGUAGE plpgsql AS $test$
BEGIN
    IF NEW.patient_id = {patient_id} THEN RAISE EXCEPTION 'rollback de regresión {token}'; END IF;
    RETURN NEW;
END $test$;
CREATE CONSTRAINT TRIGGER {trigger} AFTER INSERT ON public.medical_consultations
DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION public.{trigger}();
""")
        trigger_installed = True
        before = aligned(patient_id)
        for service in bases:
            http(service, "POST", f"/patients/{patient_id}/diseases", {"disease": "Rollback", "treatment": "", "medication": ""}, 500)
            assert aligned(patient_id) == before
            http(service, "PUT", f"/patients/{patient_id}", {**rename, "name": "Nombre que debe revertirse"}, 500)
            assert aligned(patient_id) == before
            http(service, "DELETE", f"/patients/{patient_id}", expected=500)
            assert aligned(patient_id) == before
        sql(f"DROP TRIGGER {trigger} ON public.medical_consultations; DROP FUNCTION public.{trigger}();")
        trigger_installed = False
        checks.append("Fallo real de COMMIT revierte SQL y MD al agregar, renombrar y borrar por ambas APIs")

        http("python", "DELETE", f"/patients/{patient_id}/diseases/{first['id']}", expected=204)
        http("java", "GET", f"/patients/{patient_id}/diseases/{first['id']}", expected=404)
        aligned(patient_id)
        for index, item in enumerate(created):
            http("python" if index else "java", "DELETE", f"/patients/{item}", expected=204)
            for service in bases:
                http(service, "GET", f"/patients/{item}", expected=404)
            assert not md_files(item)
            assert not query(f"SELECT id FROM public.patient_diseases WHERE patient_id={item}")
            assert query(f"SELECT id FROM public.medical_consultations WHERE patient_id={item} AND kind='deleted'")
        checks.append("Borrado compartido elimina MD y filas activas, conservando respaldo e historial")

        columns = query("SELECT column_name, data_type FROM information_schema.columns WHERE table_schema='public' AND table_name='transaction_logs'")
        assert [c["column_name"] for c in columns if c["data_type"] == "uuid"] == ["id"]
        assert not {"request_id", "execution_id"} & {c["column_name"] for c in columns}
        expected = Counter(tuple(call[key] for key in ("service", "method", "path", "http_status", "patient_id")) for call in calls if call["patient_id"] in created)
        actual = Counter()
        for _ in range(30):
            rows = query(f"SELECT service, method, path, http_status, patient_id FROM public.transaction_logs WHERE patient_id IN ({','.join(map(str, created))})")
            actual = Counter(tuple(row[key] for key in ("service", "method", "path", "http_status", "patient_id")) for row in rows)
            if actual == expected:
                break
            time.sleep(0.1)
        assert actual == expected, {"missing": list((expected - actual).items()), "extra": list((actual - expected).items())}
        checks.append(f"Una fila auditada por cada operación ({sum(actual.values())}), un UUID y patient_id conservado")
        report.update(status="PASS", patient_ids=created, http_requests=len(calls), audit_rows=sum(actual.values()))
    except BaseException as error:
        report.update(status="FAIL", error=repr(error), patient_ids=created, http_requests=len(calls))
        raise
    finally:
        cleanup_errors = []
        if trigger_installed:
            try:
                sql(f"DROP TRIGGER IF EXISTS {trigger} ON public.medical_consultations; DROP FUNCTION IF EXISTS public.{trigger}();")
            except Exception as error:
                cleanup_errors.append(repr(error))
        for item in created:
            try:
                if query(f"SELECT id FROM public.patients WHERE id={item}"):
                    http("java", "DELETE", f"/patients/{item}", expected=204)
            except Exception as error:
                cleanup_errors.append(repr(error))
        report["cleanup_errors"] = cleanup_errors
        report["finished_at"] = datetime.now(timezone.utc).isoformat()
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
