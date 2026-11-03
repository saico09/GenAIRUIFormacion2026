"""Ensayo explícito: detiene genai y puede recrear solo PostgreSQL conservando su volumen."""

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import time

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
PWSH = r"C:\Program Files\WindowsApps\Microsoft.PowerShell_7.6.9.0_x64__8wekyb3d8bbwe\pwsh.exe"


def inspect(name):
    # El objeto completo queda en memoria; nunca se escriben Env ni credenciales.
    raw = subprocess.check_output(["docker", "inspect", name], cwd=REPO, timeout=15)
    obj = json.loads(raw)[0]
    return {"id": obj["Id"], "started_at": obj["State"]["StartedAt"],
            "mounts": obj["Mounts"], "networks": obj["NetworkSettings"]["Networks"]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--nombre", required=True)
    parser.add_argument("--recrear-postgres", action="store_true")
    options = parser.parse_args()
    if not options.nombre.replace("-", "").isalnum():
        parser.error("Usa un nombre simple con letras, números y guiones.")
    output = HERE / f"{options.nombre}.json"
    if output.exists():
        parser.error("Usa un nombre nuevo para conservar la evidencia.")
    env = os.environ.copy()
    env["PATH"] = str(REPO / ".local/bin") + os.pathsep + env["PATH"]
    record = {"started_at": datetime.now(timezone.utc).isoformat(), "steps": [],
              "recreate_postgres": options.recrear_postgres, "result": "FAIL"}

    def run(label, args, timeout):
        log = HERE / f"{options.nombre}-{label}.txt"
        started = time.monotonic()
        with log.open("xb") as stream:
            result = subprocess.run(args, cwd=REPO, env=env, stdin=subprocess.DEVNULL,
                                    stdout=stream, stderr=subprocess.STDOUT, timeout=timeout)
        step = {"step": label, "exit_code": result.returncode,
                "seconds": round(time.monotonic() - started, 3), "log": log.name}
        record["steps"].append(step)
        print(json.dumps(step), flush=True)
        result.check_returncode()

    try:
        record["postgres_before"] = inspect("genairuiformacion2026-postgres-1")
        run("detener-perfil", [str(REPO / ".local/bin/minikube.exe"), "stop", "--profile=genai"], 120)
        if options.recrear_postgres:
            run("recrear-postgres", ["docker", "compose", "up", "-d", "--no-deps", "--force-recreate",
                                      "--wait", "--wait-timeout", "120", "postgres"], 180)
            recreated = inspect("genairuiformacion2026-postgres-1")
            record["postgres_recreated"] = recreated
            assert recreated["id"] != record["postgres_before"]["id"]
            assert recreated["mounts"] == record["postgres_before"]["mounts"], "El volumen cambió"
            assert "genai" not in recreated["networks"], "La prueba necesita una conexión por reponer"
        run("reanudar", [PWSH, "-NoProfile", "-File", "scripts/reanudar_minikube.ps1"], 720)
        after = inspect("genairuiformacion2026-postgres-1")
        record["postgres_after"] = after
        assert after["mounts"] == record["postgres_before"]["mounts"]
        assert after["networks"]["genai"]["IPAddress"] == "192.168.49.10"
        assert after["networks"]["genai"]["GwPriority"] == -1
        assert after["networks"]["genairuiformacion2026_default"]["GwPriority"] == 0
        record["node_networks"] = inspect("genai")["networks"]
        assert list(record["node_networks"]) == ["genai"], "El nodo debe conservar una sola red"
        record["result"] = "PASS"
    except Exception as error:
        record["error"] = f"{type(error).__name__}: {error}"
        raise
    finally:
        record["finished_at"] = datetime.now(timezone.utc).isoformat()
        output.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(json.dumps({"result": record["result"], "evidence": output.name}), flush=True)


if __name__ == "__main__":
    main()
