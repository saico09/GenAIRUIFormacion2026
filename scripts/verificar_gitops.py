"""Espera una revisión de Git en Argo CD y comprueba réplicas y un paciente real."""

import argparse
import json
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import urlopen


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--commit", required=True)
    parser.add_argument("--replicas", required=True, type=int)
    parser.add_argument("--output", required=True)
    parser.add_argument("--timeout", type=int, default=300)
    args = parser.parse_args()
    kubectl = Path(__file__).resolve().parents[1] / ".local/bin/kubectl.exe"

    def get(namespace, kind, name=None, selector=None):
        command = [str(kubectl), "--context=genai", "-n", namespace, "get", kind]
        if name:
            command.append(name)
        if selector:
            command.extend(["-l", selector])
        output = subprocess.check_output(command + ["--ignore-not-found", "-o", "json"],
                                         encoding="utf-8")
        return json.loads(output) if output.strip() else None

    deadline = time.monotonic() + args.timeout
    while True:
        application = get("argocd", "application", "fastapi") or {}
        status = application.get("status", {})
        deployment = get("genai", "deployment", "fastapi") or {}
        pods = get("genai", "pods", selector="app=fastapi")["items"]
        active = [pod for pod in pods if not pod["metadata"].get("deletionTimestamp")]
        ready = [pod for pod in active if any(
            condition["type"] == "Ready" and condition["status"] == "True"
            for condition in pod.get("status", {}).get("conditions", [])
        )]
        if (status.get("sync", {}).get("revision") == args.commit
                and status.get("sync", {}).get("status") == "Synced"
                and status.get("health", {}).get("status") == "Healthy"
                and status.get("operationState", {}).get("phase") == "Succeeded"
                and status.get("operationState", {}).get("syncResult", {}).get("revision") == args.commit
                and deployment.get("spec", {}).get("replicas") == args.replicas
                and len(active) == len(ready) == args.replicas):
            break
        if time.monotonic() >= deadline:
            raise RuntimeError(f"No coincide la revisión/estado/réplicas: {status.get('sync')}, "
                               f"{status.get('health')}, {len(ready)}/{len(active)} pods Ready; "
                               f"operación {status.get('operationState', {}).get('phase')}: "
                               f"{status.get('operationState', {}).get('message')}")
        time.sleep(2)

    operation = status["operationState"]
    assert datetime.fromisoformat(operation["finishedAt"]) >= datetime.fromisoformat(operation["startedAt"])
    responses = {}
    for name, url in (("minikube", "http://localhost:8002/patients/1"),
                      ("compose", "http://localhost:8000/patients/1")):
        with urlopen(url, timeout=15) as response:
            assert response.status == 200
            responses[name] = {"url": url, "status": response.status, "body": json.load(response)}
    assert responses["minikube"]["body"] == responses["compose"]["body"]
    assert responses["minikube"]["body"]["name"] == "Ana Demo"
    evidence = {
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "commit": args.commit, "replicas": args.replicas,
        "sync": status["sync"], "health": status["health"],
        "operation": status["operationState"],
        "pods": [{"name": pod["metadata"]["name"], "uid": pod["metadata"]["uid"],
                  "ready": True, "node": pod["spec"]["nodeName"],
                  "image": pod["spec"]["containers"][0]["image"]} for pod in ready],
        "responses": responses,
    }
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"OK {args.commit}: Synced/Healthy, operación Succeeded, {len(ready)} pods Ready y paciente HTTP 200")


if __name__ == "__main__":
    main()
