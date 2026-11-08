"""Ensayo real del montaje compartido; usar sólo con Compose principal y GitOps listos.

python scripts/verificar_historias_minikube.py --output ejecuciones/gitops-historias.json
Agrega --exercise-mount-loss para interrumpir y recuperar su propio proceso 9p.
Prueba stop/start del perfil genai, conserva volúmenes y elimina sólo su paciente.
Los respaldos históricos y la auditoría de sus operaciones se conservan.
No publica Git, no instala el chart ni hace inferencias del LLM.
"""

from __future__ import annotations

import argparse
import base64
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from uuid import uuid4


ROOT = Path(__file__).resolve().parents[1]
HISTORIES = ROOT / "datos/historias"
KUBECTL = ROOT / ".local/bin/kubectl.exe"
MINIKUBE = ROOT / ".local/bin/minikube.exe"
IMAGE = "genai-fastapi:s09-pacientes-compartidos-20261107"
BASES = {"minikube": "http://127.0.0.1:8002", "python": "http://127.0.0.1:8000", "java": "http://127.0.0.1:8080"}


def digest(value) -> str:
    data = value if isinstance(value, bytes) else json.dumps(value, ensure_ascii=False, sort_keys=True).encode()
    return hashlib.sha256(data).hexdigest()


def run(command, *, data=None, timeout=600):
    result = subprocess.run([str(part) for part in command], input=data, text=True, encoding="utf-8",
                            capture_output=True, cwd=ROOT, timeout=timeout)
    if result.returncode:
        raise RuntimeError(f"{Path(str(command[0])).name} terminó con {result.returncode}: {result.stderr[-1800:]} {result.stdout[-1800:]}")
    return result.stdout


def ps(code):
    encoded = base64.b64encode(code.encode("utf-16-le")).decode()
    return run(["pwsh", "-NoProfile", "-NonInteractive", "-EncodedCommand", encoded])


def helper():
    path = (ROOT / "scripts/montar_historias_minikube.ps1").as_posix().replace("'", "''")
    output = ps(f"$result = & '{path}'; $result | ConvertTo-Json -Compress")
    return json.loads(next(line for line in reversed(output.splitlines()) if line.startswith("{")))


def resume():
    print("Reanudando perfil y recuperando montaje/túneles...", flush=True)
    return run(["pwsh", "-NoProfile", "-NonInteractive", "-File", ROOT / "scripts/reanudar_minikube.ps1"])


def kube(namespace, kind, name=None):
    command = [KUBECTL, "--context=genai", "-n", namespace, "get", kind]
    if name:
        command.append(name)
    return json.loads(run(command + ["-o", "json"], timeout=30))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--commit", help="Exige además Argo Synced/Healthy con esta revisión")
    parser.add_argument("--exercise-mount-loss", action="store_true")
    args = parser.parse_args()
    token = uuid4().hex
    calls, checks = [], []
    report = {"started_at": datetime.now(timezone.utc).isoformat(), "run": token, "checks": checks, "calls": calls}
    patient_id = None
    patient_attempted = False
    baseline = None
    needs_resume = False
    marker = HISTORIES / ".genai-shared"
    marker_backup = HISTORIES / f".mount-probe-{token}.marker"
    original_marker = None
    postgres = run(["docker", "compose", "ps", "-q", "postgres"], timeout=30).strip()
    if not postgres or "\n" in postgres:
        raise RuntimeError("Se necesita el PostgreSQL del Compose principal")

    def http(service, method, path, body=None, expected=200, timeout=30):
        payload = None if body is None else json.dumps(body, ensure_ascii=False).encode()
        request = Request(BASES[service] + path, data=payload, method=method,
                          headers={"Content-Type": "application/json"})
        try:
            response = urlopen(request, timeout=timeout)
        except HTTPError as error:
            response = error
        with response:
            status, raw = response.status, response.read()
        result = json.loads(raw) if raw else None
        calls.append({"service": service, "method": method, "path": path, "status": status})
        assert status == expected, (service, method, path, status, result)
        return result

    def query(statement):
        text = run(["docker", "exec", "-i", postgres, "sh", "-c",
                    'psql -X -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" -At'],
                   data=f"SELECT COALESCE(json_agg(t), '[]'::json) FROM ({statement}) t;", timeout=30)
        return json.loads(text.strip())

    def snapshot(ids=None):
        patients = query("SELECT * FROM public.patients ORDER BY id")
        ids = [item["id"] for item in patients] if ids is None else ids
        where = ",".join(str(int(item)) for item in ids) or "-1"
        return {
            "patient_ids": ids,
            "patients": digest(patients),
            "diseases": digest(query(f"SELECT * FROM public.patient_diseases WHERE patient_id IN ({where}) ORDER BY id")),
            "consultations": digest(query(f"SELECT * FROM public.medical_consultations WHERE patient_id IN ({where}) ORDER BY storage_order")),
            "files": {path.name: digest(path.read_bytes()) for path in sorted(HISTORIES.glob("*.md"))},
        }

    def aligned():
        history = http("java", "GET", f"/patients/{patient_id}/history")
        assert Path(history["filename"]).name == history["filename"]
        path = HISTORIES / history["filename"]
        assert path.read_text(encoding="utf-8") == history["markdown"]
        latest = query(f"SELECT markdown_content,filename,revision FROM public.medical_consultations WHERE patient_id={patient_id} ORDER BY storage_order DESC LIMIT 1")[0]
        assert latest == {"markdown_content": history["markdown"], "filename": history["filename"], "revision": history["revision"]}
        rows = query(f"SELECT id::text,disease,treatment,medication FROM public.patient_diseases WHERE patient_id={patient_id} ORDER BY id")
        assert rows == sorted(history["entries"], key=lambda entry: entry["id"])
        for service in BASES:
            entries = http(service, "GET", f"/patients/{patient_id}/diseases")
            assert [{key: entry[key] for key in ("id", "disease", "treatment", "medication")} for entry in sorted(entries, key=lambda entry: entry["id"])] == rows
        return history

    def pods_read(history):
        pods = [pod for pod in kube("genai", "pods")["items"]
                if pod["metadata"].get("labels", {}).get("app") == "fastapi" and not pod["metadata"].get("deletionTimestamp")]
        assert len(pods) == 2
        results = []
        for pod in pods:
            assert any(condition["type"] == "Ready" and condition["status"] == "True" for condition in pod["status"]["conditions"])
            container = next(item for item in pod["spec"]["containers"] if item["name"] == "fastapi")
            assert container["image"] == IMAGE
            result = json.loads(run([KUBECTL, "--context=genai", "-n", "genai", "exec", "-i", pod["metadata"]["name"], "--", "python", "-", history["filename"]], data="""
import hashlib,json,os,sys
from pathlib import Path
directory=Path('/datos/historias')
print(json.dumps({'uid':os.getuid(),'gid':os.getgid(),'marker':(directory/'.genai-shared').read_text(),'sha256':hashlib.sha256((directory/sys.argv[1]).read_bytes()).hexdigest()}))
""", timeout=30))
            assert result == {"uid": 10001, "gid": 10001, "marker": "genai-historias-v1", "sha256": digest((HISTORIES / history["filename"]).read_bytes())}
            results.append({"name": pod["metadata"]["name"], "pod_uid": pod["metadata"]["uid"], "image": container["image"], **result})
        return results

    try:
        for service in BASES:
            http(service, "GET", "/health")
        deployment = kube("genai", "deployment", "fastapi")
        spec = deployment["spec"]["template"]["spec"]
        assert spec["securityContext"]["runAsUser"] == spec["securityContext"]["runAsGroup"] == 10001
        assert next(item for item in spec["volumes"] if item["name"] == "histories")["hostPath"] == {"path": "/mnt/genai-historias", "type": "Directory"}
        container = next(item for item in spec["containers"] if item["name"] == "fastapi")
        assert container["image"] == IMAGE
        assert {item["name"]: item.get("value") for item in container["env"]}["HISTORY_SHARED_MARKER"] == "/datos/historias/.genai-shared"
        baseline = snapshot()
        report["baseline"] = baseline
        original_marker = marker.read_bytes()
        assert original_marker == b"genai-historias-v1"
        mount_before, mount_after = helper(), helper()
        assert mount_before["Reused"] and mount_after["Reused"]
        assert mount_before["ProcessId"] == mount_after["ProcessId"] and mount_before["NodeId"] == mount_after["NodeId"]
        report["mount_reused"] = mount_after
        checks.append("Dos ejecuciones del helper reutilizan proceso y montaje comprobados")

        patient_attempted = True
        patient = http("minikube", "POST", "/patients", {"name": f"Minikube temporal {token[:8]}", "birth_date": "1990-01-01", "email": f"minikube-{token}@example.com"}, 201)
        patient_id = patient["id"]
        report["temporary_patient"] = patient_id
        assert len(list(HISTORIES.glob(f"paciente-{patient_id}-*.md"))) == 1
        for service in BASES:
            assert http(service, "GET", f"/patients/{patient_id}") == patient
        first = http("minikube", "POST", f"/patients/{patient_id}/diseases", {"disease": "Rinitis alérgica de prueba", "treatment": "Control del polen", "medication": "Cetirizina"}, 201)
        second = http("java", "POST", f"/patients/{patient_id}/diseases", {"disease": "Reflujo de prueba", "treatment": "Evitar comidas antes de acostarse", "medication": "Omeprazol"}, 201)
        http("java", "PUT", f"/patients/{patient_id}/diseases/{first['id']}", {"disease": first["disease"], "treatment": "Control del polen actualizado", "medication": "Cetirizina"})
        http("minikube", "PUT", f"/patients/{patient_id}/diseases/{second['id']}", {"disease": second["disease"], "treatment": "Plan actualizado desde Minikube", "medication": "Omeprazol"})
        consultation_id = str(uuid4())
        http("java", "POST", f"/patients/{patient_id}/consultations", {"id": consultation_id, "question": "Nota sintética de prueba " + token, "direct_answer": "Respuesta fija de prueba.", "rag_answer": "Respuesta fija de prueba.", "model": "fixture-sin-LLM", "sources": []}, 201)
        before_rename = aligned()
        http("minikube", "PUT", f"/patients/{patient_id}", {"name": f"Minikube renombrado {token[:8]}", "birth_date": patient["birth_date"], "email": patient["email"]})
        current = aligned()
        assert not (HISTORIES / before_rename["filename"]).exists()
        assert consultation_id in current["markdown"]
        report["pods_before"] = pods_read(current)
        checks.append("CRUD Minikube/Java/Compose comparte UUID, archivo Windows, respaldo SQL y diario; ambas réplicas leen el mismo contenido")

        stable = digest(current["markdown"].encode())
        os.replace(marker, marker_backup)
        try:
            http("minikube", "GET", "/health", expected=503)
            http("minikube", "POST", f"/patients/{patient_id}/diseases", {"disease": "NO DEBE GUARDARSE", "treatment": "", "medication": ""}, 503)
            assert digest((HISTORIES / current["filename"]).read_bytes()) == stable
            assert len(query(f"SELECT id FROM public.patient_diseases WHERE patient_id={patient_id}")) == 2
        finally:
            os.replace(marker_backup, marker)
        http("minikube", "GET", "/health")
        checks.append("Marcador ausente: salud y escritura503; SQL/MD sin cambios; recuperación al restaurarlo")

        if args.exercise_mount_loss:
            state_path = (ROOT / ".local/historias-mount-genai.json").as_posix().replace("'", "''")
            executable = MINIKUBE.as_posix().replace("'", "''")
            ps(f"""$ErrorActionPreference='Stop'; $s=Get-Content -Raw '{state_path}' | ConvertFrom-Json
$node=(docker inspect --format '{{{{.Id}}}}' genai).Trim(); if ($node -ne $s.nodeId) {{ throw 'Nodo distinto' }}
$p=Get-CimInstance Win32_Process -Filter "ProcessId = $($s.pid)"
if (-not $p -or $p.ExecutablePath -ne [IO.Path]::GetFullPath('{executable}') -or $p.CreationDate.ToUniversalTime().Ticks -ne ([datetime]$s.createdUtc).ToUniversalTime().Ticks -or $p.CommandLine -notlike '*--profile=genai*' -or $p.CommandLine -notlike '* mount *' -or -not $p.CommandLine.Contains($s.source + ':' + $s.target)) {{ throw 'Proceso no reconocido' }}
Stop-Process -Id $p.ProcessId -Force; Write-Output 'MOUNT_STOPPED'
""")
            needs_resume = True
            try:
                http("minikube", "GET", "/health", expected=503, timeout=10)
                report["lost_mount_health"] = 503
            except (URLError, TimeoutError, OSError) as error:
                report["lost_mount_health"] = type(error).__name__
            report["resume_after_mount_loss"] = resume()
            needs_resume = False
            assert digest(aligned()["markdown"].encode()) == stable
            report["pods_after_mount_loss"] = pods_read(aligned())
            checks.append("Pérdida del proceso9p propio: API no disponible; reanudar recupera montaje, pods y contenido")

        print("Deteniendo sólo el perfil genai para probar su reanudación...", flush=True)
        needs_resume = True
        report["stop"] = run([MINIKUBE, "stop", "--profile=genai"])
        report["resume_after_stop"] = resume()
        needs_resume = False
        assert digest(aligned()["markdown"].encode()) == stable
        report["pods_after_restart"] = pods_read(aligned())
        checks.append("Stop/start conserva paciente, registros, diario y MD/SQL compartidos")
        http("minikube", "DELETE", f"/patients/{patient_id}/diseases/{first['id']}", expected=204)
        http("java", "DELETE", f"/patients/{patient_id}/diseases/{second['id']}", expected=204)
        empty = aligned()
        assert empty["entries"] == [] and consultation_id in empty["markdown"]
        checks.append("Borrar registros por ambas APIs conserva el diario")
        if args.commit:
            report["argo_verification"] = run([os.sys.executable, ROOT / "scripts/verificar_gitops.py", "--commit", args.commit,
                                               "--replicas", "2", "--output", args.output.with_name(args.output.stem + "-argo.json")])
        report["argo"] = kube("argocd", "application", "fastapi").get("status", {})
    except Exception as error:
        report["error"] = f"{type(error).__name__}: {error}"
    finally:
        if marker_backup.exists():
            os.replace(marker_backup, marker)
        if needs_resume:
            try:
                report["recovery_in_finally"] = resume()
            except Exception as error:
                report["recovery_error"] = str(error)
        if patient_attempted and patient_id is None:
            # Si POST se confirmó pero su respuesta se perdió, localizar sólo nuestro email aleatorio.
            try:
                candidates = query(f"SELECT id FROM public.patients WHERE email='minikube-{token}@example.com'")
                assert len(candidates) <= 1
                if candidates:
                    patient_id = candidates[0]["id"]
                    report["recovered_temporary_patient"] = patient_id
            except Exception as error:
                report["cleanup_error"] = str(error)
        if patient_id is not None:
            try:
                http("java", "DELETE", f"/patients/{patient_id}", expected=204)
                assert not list(HISTORIES.glob(f"paciente-{patient_id}-*.md"))
                assert not query(f"SELECT id FROM public.patient_diseases WHERE patient_id={patient_id}")
                report["temporary_removed"] = True
            except Exception as error:
                report["cleanup_error"] = str(error)
        if baseline is not None:
            try:
                report["final"] = snapshot(baseline["patient_ids"])
                report["preserved"] = report["final"] == baseline
                assert report["preserved"], "Cambió el contenido preexistente"
            except Exception as error:
                report["preservation_error"] = str(error)
        report["passed"] = not any(key in report for key in ("error", "recovery_error", "cleanup_error", "preservation_error"))
        report["finished_at"] = datetime.now(timezone.utc).isoformat()
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(json.dumps({"passed": report["passed"], "checks": len(checks), "output": str(args.output)}), flush=True)
    if not report["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
