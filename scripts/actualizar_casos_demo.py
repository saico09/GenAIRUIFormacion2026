"""Migra sólo los tres registros demo conocidos; conserva consultas y otros registros.

Desde codigo: python -X utf8 scripts/actualizar_casos_demo.py --apply --output RUTA.json
Sin --apply sólo comprueba el plan. La salida incluye los informes previos como respaldo.
No hay transacción entre pacientes: si se interrumpe, otra ejecución retoma los pendientes.
"""

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import subprocess
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from uuid import UUID, uuid4


ROOT = Path(__file__).resolve().parents[1]
FIELDS = ("disease", "treatment", "medication")
JOURNAL = "\n## Consultas registradas\n"


def digest_fields(entry):
    fields = {key: entry[key] for key in FIELDS}
    return hashlib.sha256(json.dumps(fields, ensure_ascii=False, sort_keys=True,
                                     separators=(",", ":")).encode()).hexdigest()


def desired_entry(case):
    return {"id": case["record_id"], **{key: case[key] for key in FIELDS}}


def replace_demo(history, case):
    """Plan puro: admite únicamente el registro antiguo conocido o el nuevo exacto."""
    assert history["patient_id"] == case["patient_id"], "Propietario de historia distinto"
    matches = [entry for entry in history["entries"] if entry["id"] == case["record_id"]]
    assert len(matches) == 1, "Falta el UUID demo o está repetido; no se modifica la historia"
    desired = desired_entry(case)
    if matches[0] == desired:
        return history["markdown"], "already_current"
    assert digest_fields(matches[0]) == case["legacy_entry_sha256"], "El registro demo tiene cambios locales; se conserva"
    # Java renderiza LF al guardar; los archivos semilla pueden llegar con CRLF.
    # Sólo cambia la representación del salto, nunca el texto de las consultas.
    markdown = history["markdown"].replace("\r\n", "\n")
    clinical, separator, journal = markdown.partition(JOURNAL)
    identifier = re.escape(str(UUID(case["record_id"])))
    pattern = re.compile(rf"^## Registro {identifier}\n.*?(?=^## Registro |\Z)", re.M | re.S)
    found = list(pattern.finditer(clinical))
    assert len(found) == 1, "No se pudo identificar el bloque Markdown demo"
    original = found[0].group()
    trailing = original[len(original.rstrip("\n")):]
    replacement = (f"## Registro {case['record_id']}\n\n### Enfermedad\n{case['disease']}"
                   f"\n\n### Tratamiento\n{case['treatment']}\n\n### Medicamento\n{case['medication']}" + trailing)
    updated = clinical[:found[0].start()] + replacement + clinical[found[0].end():] + separator + journal
    assert updated.partition(JOURNAL)[1:] == markdown.partition(JOURNAL)[1:], "El diario debe conservarse exactamente"
    return updated, "replace_legacy"


def request(base, path, method="GET", body=None, execution=None):
    headers = {"Content-Type": "application/json", "X-Execution-ID": execution or str(uuid4())}
    data = None if body is None else json.dumps(body, ensure_ascii=False).encode()
    req = Request(base.rstrip("/") + path, data=data, headers=headers, method=method)
    try:
        response = urlopen(req, timeout=180)
    except HTTPError as error:
        raise RuntimeError(f"{method} {path}: HTTP {error.code}; {error.read().decode('utf-8')}") from error
    with response:
        return json.load(response)


def sql_backup(compose_dir, patient_id):
    assert type(patient_id) is int and patient_id in (1, 2, 3)
    query = ("SELECT row_to_json(t) FROM (SELECT revision,markdown_content FROM public.medical_consultations "
             f"WHERE patient_id={patient_id} ORDER BY storage_order DESC LIMIT 1) t;")
    result = subprocess.run(["docker", "compose", "exec", "-T", "postgres", "sh", "-c",
                             'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -At'],
                            input=query, cwd=compose_dir, text=True, encoding="utf-8", capture_output=True, check=True)
    return json.loads(result.stdout)


def validate_after(before, after, case, expected_markdown):
    expected_entries = [desired_entry(case) if entry["id"] == case["record_id"] else entry
                        for entry in before["entries"]]
    assert after["patient_id"] == before["patient_id"] and after["filename"] == before["filename"]
    assert after["entries"] == expected_entries, "Cambió otro registro o su orden"
    assert after["consultations"] == before["consultations"], "Cambió el historial de consultas"
    assert after["markdown"] == expected_markdown, "El Markdown guardado difiere del plan"
    assert after["revision"] == hashlib.sha256(after["markdown"].encode()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--java-url", default="http://127.0.0.1:8080")
    parser.add_argument("--python-url", default="http://127.0.0.1:8000")
    parser.add_argument("--dataset", type=Path, default=ROOT / "datos/casos_clinicos.json")
    parser.add_argument("--compose-dir", type=Path, default=ROOT)
    parser.add_argument("--skip-sync", action="store_true", help="Sólo migrar informes; sincronizar Qdrant después")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("La evidencia ya existe; usa otra salida")
    dataset = json.loads(args.dataset.read_text(encoding="utf-8-sig"))
    cases = dataset["cases"]
    assert [case["patient_id"] for case in cases] == [1, 2, 3]
    report = {"started_at": datetime.now(timezone.utc).isoformat(), "dataset_version": dataset["version"],
              "result": "PREFLIGHT", "apply": args.apply, "patients": [], "writes": 0}

    def save():
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    try:
        # Los tres pacientes se validan antes de la primera escritura.
        for case in cases:
            pid = case["patient_id"]
            patient = request(args.java_url, f"/patients/{pid}")
            assert all(patient[key] == case[key] for key in ("name", "email", "birth_date")), "El ID pertenece a otro paciente"
            before = request(args.java_url, f"/patients/{pid}/history")
            markdown, action = replace_demo(before, case)
            report["patients"].append({"patient_id": pid, "action": action, "before": before,
                                       "line_endings_normalized": action == "replace_legacy" and "\r\n" in before["markdown"],
                                       "planned_markdown": markdown, "execution_id": str(uuid4())})
        save()
        if args.apply:
            for row, case in zip(report["patients"], cases, strict=True):
                pid = case["patient_id"]
                if row["action"] == "replace_legacy":
                    after = request(args.java_url, f"/patients/{pid}/history", "PUT", {
                        "revision": row["before"]["revision"], "markdown": row["planned_markdown"],
                        "confirmed": True}, row["execution_id"])
                    report["writes"] += 1
                else:
                    after = request(args.java_url, f"/patients/{pid}/history")
                validate_after(row["before"], after, case, row["planned_markdown"])
                backup = sql_backup(args.compose_dir, pid)
                assert backup["markdown_content"] == after["markdown"] and backup["revision"] == after["revision"], "Respaldo SQL distinto"
                row["after_revision"] = after["revision"]
                row["sql_backup_matches"] = True
                row["journal_and_other_records_preserved"] = True
                assert replace_demo(after, case)[1] == "already_current"
                row["repeat_plan_is_noop"] = True
                save()
                if not args.skip_sync:
                    row["sync"] = request(args.python_url, f"/clinical/patients/{pid}/sync", "POST", execution=row["execution_id"])
                save()
        report["result"] = "PASS" if args.apply else "PLAN_VALIDATED"
    except Exception as error:
        report["result"] = "FAIL"
        report["error"] = str(error)
        raise
    finally:
        report["finished_at"] = datetime.now(timezone.utc).isoformat()
        save()
    print(json.dumps({"result": report["result"], "writes": report["writes"], "patients": len(report["patients"])}, ensure_ascii=False))


if __name__ == "__main__":
    main()
