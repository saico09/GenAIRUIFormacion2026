"""Integra Java/Markdown/Qdrant con temporales propios. --proposals usa el LLM real."""

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from uuid import NAMESPACE_URL, UUID, uuid4, uuid5


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--python-url", default="http://127.0.0.1:8000")
    parser.add_argument("--java-url", default="http://127.0.0.1:8080")
    parser.add_argument("--qdrant-url", default="http://127.0.0.1:6333")
    parser.add_argument("--collection", default="historias")
    parser.add_argument("--history-dir", type=Path, default=Path("datos/historias"))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--proposals", action="store_true", help="Dos notas ficticias, ejecutar con Ollama libre")
    parser.add_argument("--check-qdrant-error", action="store_true",
                        help="Proceso aislado compose exec: handler real con transporte Qdrant inaccesible")
    args = parser.parse_args()
    urls = {"python": args.python_url.rstrip("/"), "java": args.java_url.rstrip("/"), "qdrant": args.qdrant_url.rstrip("/")}
    marker = "Clinica QA " + uuid4().hex[:12]
    checks = []
    report = {"checks": checks, "proposals_requested": args.proposals, "qdrant_error_requested": args.check_qdrant_error}
    patient = None
    indexed = False

    def request(service, method, path, data=None, expected=200):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8") if data is not None else None
        req = Request(urls[service] + path, data=body, headers={"Content-Type": "application/json"}, method=method)
        try:
            response = urlopen(req, timeout=360)
        except HTTPError as error:
            response = error
        with response:
            raw = response.read()
            allowed = (expected,) if isinstance(expected, int) else expected
            assert response.status in allowed, f"{service} {method} {path}: {response.status}, esperado {expected}"
            return json.loads(raw) if raw else None

    def digest(data):
        return hashlib.sha256(json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()

    def points():
        rows, offset = [], None
        while True:
            body = {"limit": 100, "with_payload": True, "with_vector": True}
            if offset is not None:
                body["offset"] = offset
            result = request("qdrant", "POST", f"/collections/{args.collection}/points/scroll", body)["result"]
            rows.extend(result["points"])
            offset = result.get("next_page_offset")
            if offset is None:
                return sorted(rows, key=lambda row: str(row["id"]))

    def own_points():
        return [row for row in points() if row["payload"]["patient_id"] == patient["id"]]

    def files():
        return {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in args.history_dir.glob("*.md")}

    def history():
        value = request("java", "GET", f"/patients/{patient['id']}/history")
        assert value["revision"] == hashlib.sha256(value["markdown"].encode("utf-8")).hexdigest()
        return value

    def append(current, suffix):
        return request("java", "POST", f"/patients/{patient['id']}/history/entries", {
            "revision": current["revision"], "confirmed": True,
            "disease": f"Enfermedad Ensayo {suffix}", "treatment": f"Tratamiento Ensayo {suffix}",
            "medication": f"Medicamento Ensayo {suffix}",
        }, 201)

    def sync(expected_count):
        nonlocal indexed
        indexed = True  # También limpiar si la sincronización falló después de una escritura parcial.
        value = request("python", "POST", f"/clinical/patients/{patient['id']}/sync")
        assert value["fragments"] == expected_count and value["patient_id"] == patient["id"]
        rows = own_points()
        assert len(rows) == expected_count
        current = history()
        expected = {
            str(uuid5(NAMESPACE_URL, f"genai:java:historia:{patient['id']}:{entry['id']}:{section}")):
            (entry["id"], section, entry[field] or "No registrado.")
            for entry in current["entries"]
            for section, field in (("Enfermedad", "disease"), ("Tratamiento", "treatment"), ("Medicamento", "medication"))
        }
        for row in rows:
            payload = row["payload"]
            assert payload["registry"] == "java" and payload["revision"] == current["revision"]
            assert payload["source"] == current["filename"]
            assert (payload["record_id"], payload["section"], payload["text"]) == expected[row["id"]]
        return rows

    before_patients = {name: request(name, "GET", "/patients") for name in ("python", "java")}
    before_points = points()
    before_files = files()
    report["before"] = {name: {"count": len(rows), "sha256": digest(rows)} for name, rows in before_patients.items()}
    report["before"]["qdrant"] = {"count": len(before_points), "sha256": digest(before_points)}
    report["before"]["markdown"] = {"count": len(before_files), "sha256": digest(before_files)}
    try:
        patient = request("java", "POST", "/patients", {
            "name": marker, "birth_date": "1995-05-05", "email": "clinica-qa@example.com",
        }, 201)
        assert patient["id"] not in {row["id"] for row in before_patients["java"]}
        assert patient["id"] not in {row["id"] for row in before_patients["python"]}, "El ensayo necesita un ID inexistente en Python"
        assert not any(row["payload"]["patient_id"] == patient["id"] for row in before_points), "Ese ID ya tenía puntos: no se modifica su índice"
        request("python", "GET", f"/patients/{patient['id']}", expected=404)
        current = history()
        assert current["entries"] == []
        checks.append("Paciente temporal existe solo en Java; Markdown vacío y Python404")

        current = append(current, "Uno")
        first_id = current["entries"][0]["id"]
        assert str(UUID(first_id)) == first_id
        first_points = sync(3)
        assert sync(3) == first_points
        checks.append("Alta confirmada y sync repetido:3puntos UUID estables, mismo propietario")

        prior_revision = current["revision"]
        current = request("java", "PUT", f"/patients/{patient['id']}/history", {
            "revision": prior_revision, "confirmed": True,
            "markdown": current["markdown"].replace("Enfermedad Ensayo Uno", "Enfermedad Ensayo Editada"),
        })
        assert current["entries"][0]["id"] == first_id
        edited_points = sync(3)
        assert [row["id"] for row in edited_points] == [row["id"] for row in first_points]
        assert any(row["payload"]["text"] == "Enfermedad Ensayo Editada" for row in edited_points)
        checks.append("Editar mismo registro actualiza3puntos; no crea6")

        for confirmed, revision, expected in ((False, current["revision"], 422), (True, prior_revision, 409)):
            request("java", "POST", f"/patients/{patient['id']}/history/entries", {
                "revision": revision, "confirmed": confirmed, "disease": "No debe guardarse",
                "treatment": "", "medication": "",
            }, expected)
            assert history() == current and own_points() == edited_points
        checks.append("Cancelar y revisión antigua:422/409 sin cambios en Markdown ni índice")

        current = append(current, "Dos")
        second_id = current["entries"][1]["id"]
        assert second_id != first_id
        sync(6)
        header = current["markdown"].split("\n## Registro ", 1)[0]
        kept = current["entries"][1]
        markdown = (header + f"\n## Registro {kept['id']}\n\n### Enfermedad\n{kept['disease']}"
                    + f"\n\n### Tratamiento\n{kept['treatment']}\n\n### Medicamento\n{kept['medication']}\n")
        current = request("java", "PUT", f"/patients/{patient['id']}/history", {
            "revision": current["revision"], "confirmed": True, "markdown": markdown,
        })
        remaining = sync(3)
        assert {row["payload"]["record_id"] for row in remaining} == {second_id}
        checks.append("Segundo registro→6puntos; eliminar primero→3 sin puntos huérfanos")

        if args.check_qdrant_error:
            code = """import json,sys
from fastapi import HTTPException
from app.main import sync_clinical_history
try:
    sync_clinical_history(int(sys.argv[1]))
except HTTPException as error:
    assert error.status_code == 503
    print(json.dumps({'status':503,'scope':'handler real y transporte Qdrant fallido en proceso aislado; no HTTP externo'}))
else:
    raise AssertionError('Se esperaba fallo de transporte Qdrant')
"""
            run = subprocess.run(["docker", "compose", "exec", "-T", "-e", "QDRANT_URL=http://127.0.0.1:1",
                                  "python-api", "python", "-", str(patient["id"])], input=code, text=True,
                                 encoding="utf-8", capture_output=True, timeout=180, cwd=Path(__file__).resolve().parents[1])
            assert run.returncode == 0, "El proceso aislado no verificó el fallo Qdrant"
            result = json.loads(run.stdout.strip().splitlines()[-1])
            assert result["status"] == 503
            assert history() == current and own_points() == remaining
            report["qdrant_error"] = result
            checks.append("Qdrant inaccesible en proceso aislado→handler503; historia e índice real conservados")

        if args.proposals:
            note = "Diagnóstico registrado: Enfermedad Prueba. Tratamiento registrado: Tratamiento Prueba. Medicación registrada: Medicamento Prueba."
            answer = request("python", "POST", "/clinical/proposals", {"patient_id": patient["id"], "note": note})
            assert answer["patient_id"] == patient["id"] and answer["entries"]
            expected = {"disease": "Enfermedad Prueba", "treatment": "Tratamiento Prueba", "medication": "Medicamento Prueba"}
            assert any(all(value in entry[field] for field, value in expected.items()) for entry in answer["entries"])
            for entry in answer["entries"]:
                for field in expected:
                    if entry[field]:
                        assert entry["evidence"][field] in note and entry[field] in entry["evidence"][field]
            assert history() == current and own_points() == remaining
            absent = request("python", "POST", "/clinical/proposals", {
                "patient_id": patient["id"], "note": "¿Qué enfermedad explica el dolor de cabeza de este paciente ficticio?",
            })
            assert absent["entries"] == []
            assert history() == current and own_points() == remaining
            report["proposals"] = {"explicit_note": answer, "symptom_question": absent, "wrote_history_or_index": False}
            checks.append("Propuesta real de nota explícita y pregunta de síntomas: evidencia literal, ninguna escritura")

        pid = patient["id"]
        request("java", "DELETE", f"/patients/{pid}", expected=204)
        removed = request("python", "POST", f"/clinical/patients/{pid}/sync")
        assert removed["status"] == "removed" and removed["fragments"] == 0 and own_points() == []
        request("python", "POST", "/chat", {"patient_id": pid, "question": "Consulta ficticia"}, 404)
        request("python", "POST", "/clinical/proposals", {"patient_id": pid, "note": "Nota ficticia"}, 404)
        request("java", "GET", f"/patients/{pid}/history", expected=404)
        assert not list(args.history_dir.glob(f"paciente-{pid}-*.md"))
        patient = None
        checks.append("DELETE Java + sync→0puntos; chat/propuesta/historia404 y archivo eliminado")
        report["result"] = "passed"
    except Exception as error:
        report["result"] = "failed"
        report["error_type"] = type(error).__name__
        raise
    finally:
        if patient is not None:
            current_row = request("java", "GET", f"/patients/{patient['id']}", expected=(200, 404))
            if "id" in current_row:
                assert current_row["name"] == marker, "No se elimina un paciente ajeno al ensayo"
                request("java", "DELETE", f"/patients/{patient['id']}", expected=204)
            if indexed:
                request("python", "POST", f"/clinical/patients/{patient['id']}/sync")
        after_patients = {name: request(name, "GET", "/patients") for name in ("python", "java")}
        after_points = points()
        after_files = files()
        report["preserved"] = {"patients": after_patients == before_patients,
                               "qdrant_including_vectors": after_points == before_points,
                               "markdown_files": after_files == before_files}
        report["after"] = {name: {"count": len(rows), "sha256": digest(rows)} for name, rows in after_patients.items()}
        report["after"]["qdrant"] = {"count": len(after_points), "sha256": digest(after_points)}
        report["after"]["markdown"] = {"count": len(after_files), "sha256": digest(after_files)}
        if not all(report["preserved"].values()):
            report["result"] = "failed"
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        # La consola Windows puede usar cp1252; el archivo de evidencia conserva UTF-8.
        print(json.dumps(report, ensure_ascii=True, indent=2))
        assert all(report["preserved"].values()), "Cambiaron datos previos al ensayo"


if __name__ == "__main__":
    main()
