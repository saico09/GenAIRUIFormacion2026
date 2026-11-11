"""RAG, propuestas, guardado y auditoría reales con un paciente temporal propio.

No modifica Ana. Usa el modelo configurado en la API, sin simulaciones. Al terminar
borra sólo su paciente/índice; conserva respaldos y auditoría, como exige la app.
"""

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from time import perf_counter
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from uuid import uuid4


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--python-url", default="http://127.0.0.1:8000")
    parser.add_argument("--java-url", default="http://127.0.0.1:8080")
    parser.add_argument("--qdrant-url", default="http://127.0.0.1:6333")
    parser.add_argument("--postgres-container", default="genairuiformacion2026-postgres-1")
    parser.add_argument("--expected-model", default="gemma4:12b")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--trace", action="store_true", help="Comprueba además Phoenix/Loki con una quinta consulta del mismo temporal")
    args = parser.parse_args()
    marker = uuid4().hex[:12]
    patient = None
    report = {"started_at": datetime.now(timezone.utc).isoformat(), "scope": __doc__, "cases": [], "checks": []}
    args.output.parent.mkdir(parents=True, exist_ok=True)

    def checkpoint():
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    def http(base, method, path, payload=None, *, expected=200, execution_id=None, timeout=420):
        headers = {"Content-Type": "application/json", "X-Execution-ID": execution_id or str(uuid4())}
        request = Request(base.rstrip("/") + path, data=None if payload is None else json.dumps(payload, ensure_ascii=False).encode("utf-8"), headers=headers, method=method)
        try:
            response = urlopen(request, timeout=timeout)
        except HTTPError as error:
            response = error
        with response:
            raw = response.read()
            body = json.loads(raw) if raw else None
            assert response.status == expected, (method, path, response.status, body)
            if base != args.qdrant_url:
                assert response.headers.get("X-Execution-ID") == headers["X-Execution-ID"]
            return body

    def sql(query):
        return subprocess.check_output([
            "docker", "exec", args.postgres_container, "sh", "-c",
            'psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" -At -c "$1"', "sh", query,
        ], text=True, encoding="utf-8").strip()

    def history():
        result = http(args.java_url, "GET", f"/patients/{patient['id']}/history")
        assert hashlib.sha256(result["markdown"].encode()).hexdigest() == result["revision"]
        return result

    def points(pid):
        result = http(args.qdrant_url, "POST", "/collections/historias/points/scroll", {
            "filter": {"must": [{"key": "patient_id", "match": {"value": pid}}]},
            "limit": 100, "with_payload": True, "with_vector": True,
        })
        assert result["result"]["next_page_offset"] is None
        return sorted(result["result"]["points"], key=lambda item: str(item["id"]))

    def digest(value):
        return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True).encode()).hexdigest()

    def chat(name, question, check):
        execution_id = str(uuid4())
        start = perf_counter()
        result = http(args.python_url, "POST", "/chat", {"patient_id": patient["id"], "question": question}, execution_id=execution_id)
        row = {"name": name, "execution_id": execution_id, "question": question,
               "seconds": round(perf_counter() - start, 3), "response": result}
        report["cases"].append(row)
        checkpoint()
        assert result["model"] == args.expected_model
        assert result["consultation"]["id"] == execution_id and result["consultation"]["saved"]
        assert result["index_synced"] is True
        assert len(result["sources"]) <= 3
        assert all(source["patient_id"] == patient["id"] for source in result["sources"])
        row["semantic_passed"] = bool(check(result))
        current = history()
        assert current["entries"] == confirmed
        assert sum(item["id"] == execution_id for item in current["consultations"]) == 1
        assert question in current["markdown"]
        assert all(result[key] in current["markdown"].replace("\n> ", "\n") for key in ("direct_answer", "rag_answer"))
        row["passed"] = row["semantic_passed"]
        checkpoint()
        print(json.dumps({"case": name, "passed": row["passed"], "seconds": row["seconds"]}, ensure_ascii=False), flush=True)
        return row

    original_patients = {p["id"]: p for p in http(args.java_url, "GET", "/patients") if p["id"] in (1, 2, 3)}
    protected_vectors = {pid: digest(points(pid)) for pid in (2, 3)}
    try:
        patient = http(args.java_url, "POST", "/patients", {
            "name": f"Paciente QA {marker}", "birth_date": "1990-01-01", "email": f"consulta-{marker}@example.com",
        }, expected=201)
        report["temporary_patient_id"] = patient["id"]
        current = history()
        first = http(args.java_url, "POST", f"/patients/{patient['id']}/history/entries", {
            "revision": current["revision"], "confirmed": True,
            "disease": "Diagnóstico ficticio confirmado: Enfermedad Nube.",
            "treatment": "Plan ficticio registrado: Tratamiento Nube.",
            "medication": "Medicamento ficticio registrado: Medicamento Nube.",
        }, expected=201)
        confirmed = first["entries"]
        http(args.python_url, "POST", f"/clinical/patients/{patient['id']}/sync")
        assert len(points(patient["id"])) == 3
        report["checks"].append("Paciente y tres fragmentos confirmados propios, con UUID común")

        known = chat("tres_campos", f"Resume la enfermedad, el tratamiento y el medicamento registrados de {patient['name']}.",
                     lambda result: all(value in result["rag_answer"] for value in ("Enfermedad Nube", "Tratamiento Nube", "Medicamento Nube"))
                     and confirmed[0]["id"] in result["rag_answer"])
        chat("cirugia_ausente", f"¿Cuál fue la última cirugía registrada de {patient['name']}?",
             lambda result: result["rag_answer"].strip().rstrip(".") == "No hay información suficiente")
        symptom_note = "Desde ayer refiere cansancio y dolor de cabeza leve."
        symptom = chat("sintomas_nuevos", symptom_note,
                       lambda result: "Diagnóstico orientativo (sin confirmar)" in result["rag_answer"]
                       and "Para aclarar la consulta" not in result["rag_answer"] and "?" not in result["rag_answer"])
        chat("recuperar_consulta_anterior", "¿Qué síntomas relató el paciente en consultas anteriores?",
             lambda result: "cansancio" in result["rag_answer"].lower() and "dolor de cabeza" in result["rag_answer"].lower()
             and symptom["execution_id"] in result["rag_answer"] and "/Consulta]" in result["rag_answer"])
        report["checks"].append("Se evaluaron datos confirmados, ausencia documental, orientación y síntomas reportados; resultado semántico por caso")

        previous = history()
        repeated = http(args.python_url, "POST", "/chat", {"patient_id": patient["id"], "question": known["question"]}, execution_id=known["execution_id"])
        assert all(repeated[key] == known["response"][key] for key in ("direct_answer", "rag_answer", "sources", "model", "consultation"))
        http(args.python_url, "POST", "/chat", {"patient_id": patient["id"], "question": "Pregunta diferente con el mismo UUID"},
             execution_id=known["execution_id"], expected=409)
        assert history() == previous
        report["checks"].append("Mismo UUID recupera respuestas originales; distinto contenido devuelve 409 sin duplicados")

        note = "Diagnóstico registrado: Enfermedad Nube. Tratamiento: Tratamiento Nube. Medicamento: Medicamento Nube."
        proposal = http(args.python_url, "POST", "/clinical/proposals", {"patient_id": patient["id"], "note": note})
        assert any(all(value in item[field] for field, value in (("disease", "Enfermedad Nube"), ("treatment", "Tratamiento Nube"), ("medication", "Medicamento Nube"))) for item in proposal["entries"]), proposal
        for item in proposal["entries"]:
            for field in ("disease", "treatment", "medication"):
                if item[field]:
                    assert item[field] in item["evidence"][field] and item["evidence"][field] in note
        negative = http(args.python_url, "POST", "/clinical/proposals", {"patient_id": patient["id"],
                        "note": "No tiene Enfermedad Nube. No recibe Medicamento Nube. No tiene tratamiento registrado."})
        assert negative["entries"] == [], negative
        assert history() == previous
        report["proposals"] = {"explicit": proposal, "negative": negative}
        report["checks"].append("Propuesta real recupera tres campos con evidencia; negaciones no generan datos ni escrituras clínicas")

        final = history()
        assert len(final["consultations"]) == 4 and final["entries"] == confirmed
        assert sql(f"SELECT count(*) FROM public.medical_consultations WHERE patient_id = {patient['id']} AND kind = 'consultation'") == "4"
        sql_backup = json.loads(sql(f"SELECT json_build_object('revision',revision,'hash',encode(sha256(convert_to(markdown_content,'UTF8')),'hex'),'bytes',octet_length(markdown_content)) FROM public.medical_consultations WHERE patient_id = {patient['id']} ORDER BY storage_order DESC LIMIT 1"))
        assert sql_backup["hash"] == sql_backup["revision"] == final["revision"]
        assert sql_backup["bytes"] == len(final["markdown"].encode())
        own_points = points(patient["id"])
        assert len(own_points) == 7
        for item in own_points:
            payload = item["payload"]
            assert payload["revision"] == final["revision"]
            if payload["kind"] == "reported_consultation":
                saved = next(c for c in final["consultations"] if c["id"] == payload["record_id"])
                assert saved["question"] in payload["text"]
                assert saved["direct_answer"] not in payload["text"] and saved["rag_answer"] not in payload["text"]
        report["checks"].append("SQL respalda MD completo y revisión; Qdrant conserva tres campos y cuatro notas, sin reingerir respuestas IA")
        logs = json.loads(sql(f"SELECT json_agg(t) FROM (SELECT id::text,patient_id,service,operation,http_status,request_truncated,response_truncated FROM public.transaction_logs WHERE patient_id = {patient['id']} ORDER BY created_at) t"))
        assert {"python", "java"} <= {item["service"] for item in logs}
        assert len({item["id"] for item in logs}) == len(logs)
        chat_logs = [item for item in logs if item['service'] == 'python' and item['operation'] == 'POST /chat']
        assert sum(item['http_status'] == 200 for item in chat_logs) == 5  # 4 consultas y 1 reintento.
        assert sum(item['http_status'] == 409 for item in chat_logs) == 1
        report["sql_backup"] = sql_backup
        report["patient_logs"] = logs
        report["checks"].append("Cada operación HTTP tiene un UUID único y patient_id; el reintento conserva una sola consulta clínica")
        if args.trace:
            trace_output = args.output.with_name("regresion-traza.json")
            trace = subprocess.run([sys.executable, "-X", "utf8", str(Path(__file__).with_name("verificar_traza.py")),
                "--patient-id", str(patient["id"]), "--question", f"¿Qué enfermedad tiene registrada {patient['name']}?",
                "--expected", "Enfermedad Nube", "--prefix", "consultas-regresion", "--output", str(trace_output)],
                capture_output=True, text=True, encoding="utf-8", timeout=480)
            report["trace"] = {"passed": trace.returncode == 0, "output": str(trace_output),
                               "stdout": trace.stdout, "stderr": trace.stderr}
            checkpoint()
            assert trace.returncode == 0, report["trace"]
            report["checks"].append("Quinta consulta temporal: Phoenix raíz/cuatro nodos y Loki correlacionados")
        report["passed"] = all(row["passed"] for row in report["cases"])
        assert report["passed"], "Fallos semánticos: " + ", ".join(row["name"] for row in report["cases"] if not row["passed"])
    except BaseException as error:
        report["passed"] = False
        report["error"] = str(error)
        raise
    finally:
        if patient is not None:
            current = http(args.java_url, "GET", f"/patients/{patient['id']}")
            assert current["email"] == f"consulta-{marker}@example.com", "No se elimina un paciente ajeno"
            http(args.java_url, "DELETE", f"/patients/{patient['id']}", expected=204)
            http(args.python_url, "POST", f"/clinical/patients/{patient['id']}/sync")
            http(args.java_url, "GET", f"/patients/{patient['id']}", expected=404)
            report["temporary_patient_and_points_removed"] = not points(patient["id"])
        after = {p["id"]: p for p in http(args.java_url, "GET", "/patients") if p["id"] in original_patients}
        report["original_patients_preserved"] = after == original_patients
        report["bruno_carla_vectors_preserved"] = all(digest(points(pid)) == value for pid, value in protected_vectors.items())
        report["finished_at"] = datetime.now(timezone.utc).isoformat()
        checkpoint()
    assert report["temporary_patient_and_points_removed"] and report["original_patients_preserved"] and report["bruno_carla_vectors_preserved"]
    print(json.dumps({"passed": True, "cases": len(report["cases"]), "checks": len(report["checks"]), "cleanup": True}, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
