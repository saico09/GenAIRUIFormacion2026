"""Reemplaza un pod FastAPI por vez; aborta al primer incumplimiento.

Ejecutar en Windows desde codigo/, con Python. Solo modifica los pods FastAPI
del perfil genai; no cambia Deployment, PostgreSQL, nodos ni otros servicios.
"""

from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import time


HERE = Path(__file__).resolve().parent
KUBECTL = HERE.parents[1] / ".local/bin/kubectl.exe"
OUTPUT = HERE / "recreaciones-ruta-directa.json"
HOST = "192.168.49.10"
BASE = [str(KUBECTL), "--context=genai", "-n", "genai"]


def utc():
    return datetime.now(timezone.utc).isoformat()


def kubectl(*args, timeout=30):
    result = subprocess.run(BASE + list(args), capture_output=True, text=True,
                            encoding="utf-8", errors="replace", timeout=timeout)
    if result.returncode:
        raise RuntimeError(f"kubectl {args[0]} fallo con codigo {result.returncode}")
    return result.stdout


def get_json(*args):
    return json.loads(kubectl("get", *args, "-o", "json"))


def ready(pod):
    return not pod["metadata"].get("deletionTimestamp") and any(
        condition["type"] == "Ready" and condition["status"] == "True"
        for condition in pod.get("status", {}).get("conditions", []))


def host_of(spec):
    container = next(item for item in spec["containers"] if item["name"] == "fastapi")
    return next((item.get("value") for item in container.get("env", [])
                 if item["name"] == "POSTGRES_HOST"), None)


def pod_summary(pod):
    return {"name": pod["metadata"]["name"], "uid": pod["metadata"]["uid"],
            "ready": ready(pod), "postgres_host": host_of(pod["spec"]),
            "restarts": sum(item.get("restartCount", 0)
                            for item in pod.get("status", {}).get("containerStatuses", []))}


def snapshot():
    deployment = get_json("deployment", "fastapi")
    assert deployment["spec"]["replicas"] == 2, "El Deployment debe mantener dos replicas"
    assert host_of(deployment["spec"]["template"]["spec"]) == HOST, "Host del Deployment incorrecto"
    assert deployment["status"].get("readyReplicas") == 2, "No hay dos replicas Ready"
    pods = get_json("pods", "-l", "app=fastapi")["items"]
    active = [pod for pod in pods if not pod["metadata"].get("deletionTimestamp")]
    assert len(active) == 2 and all(ready(pod) for pod in active), "Se necesitan exactamente dos pods Ready"
    assert all(host_of(pod["spec"]) == HOST for pod in active), "Un pod conserva el host anterior"
    return sorted(active, key=lambda pod: pod["metadata"]["creationTimestamp"])


def save(report):
    OUTPUT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main():
    if OUTPUT.exists():
        raise RuntimeError("La evidencia ya existe; no se sobrescribe una ejecucion previa")
    report = {"started_utc": utc(), "context": "genai", "namespace": "genai",
              "expected_host": HOST, "planned_iterations": 8, "iterations": [], "result": "running"}
    save(report)
    try:
        kubectl("rollout", "status", "deployment/fastapi", "--timeout=300s", timeout=320)
        report["initial_pods"] = [pod_summary(pod) for pod in snapshot()]
        save(report)
        for index in range(1, 9):
            started = time.monotonic()
            item = {"iteration": index, "started_utc": utc(), "result": "running"}
            report["iterations"].append(item)
            before = snapshot()
            selected, keeper = before
            item["deleted"] = pod_summary(selected)
            item["preserved_before"] = pod_summary(keeper)
            save(report)
            kubectl("delete", "pod", selected["metadata"]["name"], "--wait=true", "--timeout=60s", timeout=80)
            preserved = get_json("pod", keeper["metadata"]["name"])
            assert preserved["metadata"]["uid"] == keeper["metadata"]["uid"] and ready(preserved), "La replica conservada dejo de estar Ready"
            item["preserved_after_delete"] = pod_summary(preserved)
            kubectl("rollout", "status", "deployment/fastapi", "--timeout=180s", timeout=200)
            after = snapshot()
            old_uids = {pod["metadata"]["uid"] for pod in before}
            replacements = [pod for pod in after if pod["metadata"]["uid"] not in old_uids]
            assert len(replacements) == 1, "No se identifico exactamente un pod nuevo"
            assert any(pod["metadata"]["uid"] == keeper["metadata"]["uid"] for pod in after), "Cambio la replica que debia conservarse"
            replacement = replacements[0]
            item["replacement"] = pod_summary(replacement)
            item["after"] = [pod_summary(pod) for pod in after]
            raw_logs = kubectl("logs", replacement["metadata"]["name"], "-c", "fastapi")
            startup = []
            for line in raw_logs.splitlines():
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(event, dict) and event.get("event") == "db_startup":
                    startup.append(event)
            log_path = HERE / f"recreaciones-ruta-directa-{index:02d}.log"
            log_path.write_text("\n".join(json.dumps(event, ensure_ascii=False) for event in startup) + "\n", encoding="utf-8")
            item["startup_events"] = startup
            item["log_file"] = log_path.name
            assert replacement["status"]["containerStatuses"][0].get("restartCount", 0) == 0, "El reemplazo reinicio su contenedor"
            assert len(startup) == 1 and startup[0].get("status") == "ready" and startup[0].get("attempts") == 1, "El arranque no fue directo en un unico intento"
            item.update(result="passed", finished_utc=utc(), elapsed_seconds=round(time.monotonic() - started, 3))
            save(report)
            print(f"Iteracion {index}/8 PASS: UID nuevo, otra replica conservada, dos Ready, DB intento1.", flush=True)
        report["result"] = "passed"
    except Exception as error:
        report["result"] = "failed"
        report["error_type"] = type(error).__name__
        # Solo se conservan mensajes de aserciones/errores propios, sin salida Kubernetes.
        if isinstance(error, (AssertionError, RuntimeError)):
            report["reason"] = str(error)
        if report["iterations"] and report["iterations"][-1]["result"] == "running":
            report["iterations"][-1]["result"] = "failed"
        raise
    finally:
        report["finished_utc"] = utc()
        save(report)


if __name__ == "__main__":
    main()
