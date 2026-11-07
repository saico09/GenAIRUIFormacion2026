"""HTTP real de historias Java; solo modifica y limpia sus pacientes temporales."""

import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import re
from threading import Barrier
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from uuid import UUID, uuid4


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8080")
    parser.add_argument("--origin", default="http://localhost:8000")
    parser.add_argument("--history-dir", type=Path, help="Directorio montado: coteja archivos anteriores y limpieza")
    parser.add_argument("--output", type=Path, help="JSON de resultado; no contiene filas previas ni textos personales")
    args = parser.parse_args()
    base = args.base_url.rstrip("/")
    checks = []
    owned = {}
    marker = "Historia QA " + uuid4().hex[:12]

    def request(method, path, payload=None, extra_headers=None):
        headers = {"Origin": args.origin, **(extra_headers or {})}
        data = None
        if payload is not None:
            data = payload if isinstance(payload, bytes) else json.dumps(payload, ensure_ascii=False).encode("utf-8")
            headers["Content-Type"] = "application/json"
        req = Request(base + path, data=data, headers=headers, method=method)
        try:
            response = urlopen(req, timeout=20)
        except HTTPError as error:
            response = error
        with response:
            body = response.read()
            return response.status, dict(response.headers.items()), body

    def api(method, path, payload=None, expected=200):
        status, headers, body = request(method, path, payload)
        assert status == expected, f"{method} {path}: {status}, esperado {expected}"
        lower = {key.lower(): value for key, value in headers.items()}
        assert lower.get("access-control-allow-origin") == args.origin
        return json.loads(body) if body else None

    def patients():
        return api("GET", "/patients")

    def files():
        if args.history_dir is None:
            return None
        return {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in args.history_dir.glob("*.md")}

    def history(pid):
        value = api("GET", f"/patients/{pid}/history")
        assert value["patient_id"] == pid
        assert hashlib.sha256(value["markdown"].encode("utf-8")).hexdigest() == value["revision"]
        assert re.fullmatch(fr"paciente-{pid}-[a-z0-9-]+\.md", value["filename"])
        for entry in value["entries"]:
            assert str(UUID(entry["id"])) == entry["id"]
        assert len({entry["id"] for entry in value["entries"]}) == len(value["entries"])
        return value

    def append(pid, current, **fields):
        return api("POST", f"/patients/{pid}/history/entries", {
            "revision": current["revision"], "confirmed": True,
            "disease": "", "treatment": "", "medication": "", **fields,
        }, 201)

    def reject_unchanged(method, path, payload, pid, expected=422):
        prior = history(pid)
        response = api(method, path, payload, expected)
        assert "detail" in response
        assert history(pid) == prior, "Una petición rechazada cambió el informe"

    before = patients()
    previous_ids = {row["id"] for row in before}
    before_files = files()
    report = {"base_url": base, "checks": checks, "previous_patient_count": len(before)}
    try:
        for suffix in ("Uno", "Dos"):
            input_data = {"name": marker + " " + suffix, "birth_date": "1995-05-05", "email": "historia-qa@example.com"}
            status, _, raw = request("POST", "/patients", input_data)
            created = json.loads(raw)
            if status == 201 and isinstance(created.get("id"), int) and created["id"] not in previous_ids:
                owned[created["id"]] = input_data
            assert status == 201 and created["id"] in owned
        one, two = owned
        first = history(one)
        second = history(two)
        assert first["entries"] == second["entries"] == []
        assert first["markdown"].endswith(f"patient_id: {one}\n")
        if args.history_dir:
            assert (args.history_dir / first["filename"]).read_text(encoding="utf-8") == first["markdown"]
        checks.append("Crear paciente crea informe vacío con SHA256 y filename seguro")

        history_path = f"/patients/{one}/history"
        entry_path = history_path + "/entries"
        invalid = {"revision": first["revision"], "confirmed": True, "disease": "Dato ficticio", "treatment": "", "medication": ""}
        for patch in ({"confirmed": False}, {"confirmed": "true"}, {"confirmed": None},
                      {"disease": ""}, {"disease": "No registrado."}, {"disease": 12},
                      {"disease": "x" * 2001}, {"disease": "Dato\n## Registro inesperado"},
                      {"disease": "Dato\u0000"}, {"revision": "no-es-sha"}):
            reject_unchanged("POST", entry_path, {**invalid, **patch}, one)
        no_confirmation = {key: value for key, value in invalid.items() if key != "confirmed"}
        reject_unchanged("POST", entry_path, no_confirmation, one)
        reject_unchanged("POST", entry_path, b"{ json invalido", one)
        checks.append("Confirmación estricta, tipos, campo vacío, controles, encabezados y 2000 caracteres")

        first = append(one, first, disease="Enfermedad QA", treatment="Tratamiento QA", medication="Medicamento QA")
        first_id = first["entries"][0]["id"]
        assert first["entries"] == [{"id": first_id, "disease": "Enfermedad QA", "treatment": "Tratamiento QA", "medication": "Medicamento QA"}]
        second = append(two, second, disease="Dato aislado QA")
        assert second["entries"][0]["treatment"] == second["entries"][0]["medication"] == ""
        assert "### Tratamiento\nNo registrado." in second["markdown"]
        checks.append("Alta de registro con UUID del servidor y vacíos No registrado")

        reject_unchanged("POST", entry_path, invalid, one, 409)
        gate = Barrier(2)
        revision = first["revision"]

        def simultaneous(label):
            gate.wait(timeout=10)
            return request("POST", entry_path, {"revision": revision, "confirmed": True,
                           "disease": label, "treatment": "", "medication": ""})[0]

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(simultaneous, ("Concurrente QA A", "Concurrente QA B")))
        assert sorted(results) == [201, 409], results
        first = history(one)
        assert len(first["entries"]) == 2
        assert history(two) == second
        checks.append("Dos escrituras con la misma revisión: exactamente una201 y una409, sin pérdida")

        replacement = {"revision": first["revision"], "markdown": first["markdown"], "confirmed": True}
        for markdown in (
            first["markdown"].replace(f"patient_id: {one}\n", f"patient_id: {two}\n"),
            first["markdown"].replace(owned[one]["name"], owned[two]["name"], 1),
            first["markdown"].replace(first_id, str(uuid4())),
            first["markdown"].replace(first_id, "uuid-invalido"),
            first["markdown"].replace(first["entries"][1]["id"], first_id),
            first["markdown"].replace("### Enfermedad", "### Diagnóstico", 1),
            first["markdown"].replace("Enfermedad QA", "x" * 2001),
            first["markdown"] + "x" * 65536,
            first["markdown"].replace("Enfermedad QA", "é" * 33000),
        ):
            reject_unchanged("PUT", history_path, {**replacement, "markdown": markdown}, one)
        reject_unchanged("PUT", history_path, {**replacement, "confirmed": False}, one)
        reject_unchanged("PUT", f"/patients/{two}/history", {**replacement, "revision": second["revision"]}, two)
        first = api("PUT", history_path, {**replacement, "markdown": first["markdown"].replace("Tratamiento QA", "Tratamiento QA editado")})
        assert first["entries"][0]["id"] == first_id
        assert first["entries"][0]["treatment"] == "Tratamiento QA editado"
        reject_unchanged("PUT", history_path, replacement, one, 409)
        checks.append("Edición conserva UUID; rechaza propietario/estructura/UUID duplicado o nuevo/64KiB y revisión antigua")

        status, headers, body = request("GET", history_path + ".md")
        lower = {key.lower(): value for key, value in headers.items()}
        assert status == 200 and lower["content-type"].startswith("text/markdown")
        assert "attachment" in lower["content-disposition"] and first["filename"] in lower["content-disposition"]
        assert "content-disposition" in lower["access-control-expose-headers"].lower()
        assert body.decode("utf-8") == first["markdown"]
        assert hashlib.sha256(body).hexdigest() == first["revision"]
        checks.append("Descarga Markdown exacta y Content-Disposition accesible mediante CORS")

        old_filename = first["filename"]
        edited = {**owned[one], "name": marker + " Renombrado"}
        api("PUT", f"/patients/{one}", edited)
        owned[one] = edited
        renamed = history(one)
        assert renamed["filename"] != old_filename and renamed["entries"] == first["entries"]
        assert renamed["revision"] != first["revision"]
        assert renamed["markdown"].startswith("# Historia clínica ficticia — " + edited["name"] + "\n")
        if args.history_dir:
            assert not (args.history_dir / old_filename).exists()
            assert (args.history_dir / renamed["filename"]).exists()
        assert history(two) == second
        checks.append("Renombrar paciente cambia filename y título, conserva registros y otro paciente")

        for index in range(1, 50):
            second = append(two, second, disease=f"Límite QA {index}")
        assert len(second["entries"]) == 50
        reject_unchanged("POST", f"/patients/{two}/history/entries", {
            "revision": second["revision"], "confirmed": True,
            "disease": "Exceso QA", "treatment": "", "medication": "",
        }, two)
        header = second["markdown"].split("\n## Registro ", 1)[0]
        second = api("PUT", f"/patients/{two}/history", {"revision": second["revision"], "markdown": header, "confirmed": True})
        assert second["entries"] == []
        checks.append("Límite50: acepta50, rechaza51 sin cambios; edición permite quitar registros existentes")

        api("DELETE", f"/patients/{one}", expected=204)
        del owned[one]
        for suffix in ("", "/history", "/history.md"):
            assert request("GET", f"/patients/{one}" + suffix)[0] == 404
        assert history(two) == second
        if args.history_dir:
            assert not list(args.history_dir.glob(f"paciente-{one}-*.md"))
        checks.append("Borrar paciente elimina solamente su informe; GET posteriores404")
        report["result"] = "passed"
    except Exception as error:
        report["result"] = "failed"
        report["error_type"] = type(error).__name__
        raise
    finally:
        for pid, expected in list(owned.items()):
            current = api("GET", f"/patients/{pid}")
            assert current == {"id": pid, **expected}, "No se elimina un paciente ajeno a esta prueba"
            api("DELETE", f"/patients/{pid}", expected=204)
            del owned[pid]
        report["previous_patients_preserved"] = patients() == before
        report["previous_files_preserved"] = files() == before_files if args.history_dir else None
        report["temporary_patients_remaining"] = len(owned)
        if not report["previous_patients_preserved"] or report["previous_files_preserved"] is False:
            report["result"] = "failed"
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(report, ensure_ascii=True, indent=2))
        assert report["previous_patients_preserved"] and report["previous_files_preserved"] is not False


if __name__ == "__main__":
    main()
