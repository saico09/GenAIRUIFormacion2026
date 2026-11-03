"""Captura de solo lectura: huellas de pacientes y estado de Minikube, sin secretos."""

import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import time
from urllib.error import HTTPError
from urllib.request import Request, urlopen


HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
KUBECTL = REPO / ".local/bin/kubectl.exe"
CANONICAL = (
    "SHA-256 de UTF-8 JSON de la lista completa ordenada por id; claves ordenadas, "
    "ensure_ascii=False, separators=(coma,dos_puntos), allow_nan=False. "
    "No se guardan cuerpos de pacientes."
)


def now():
    return datetime.now(timezone.utc).isoformat()


def sha(data):
    return hashlib.sha256(data).hexdigest()


def http_probe(name, url):
    result = {"url": url, "read_at": now()}
    started = time.monotonic()
    try:
        count = name == "qdrant_points"
        request = Request(url, data=b'{"exact":true}' if count else None,
                          headers={"Content-Type": "application/json"} if count else {})
        with urlopen(request, timeout=20) as response:
            value = json.load(response)
            result["status"] = response.status
        if name.endswith("patients"):
            assert isinstance(value, list), "Expected patient list"
            canonical = json.dumps(sorted(value, key=lambda row: row["id"]),
                                   sort_keys=True, ensure_ascii=False,
                                   separators=(",", ":"), allow_nan=False).encode("utf-8")
            result.update(count=len(value), sha256_canonical=sha(canonical),
                          fields=sorted({key for row in value for key in row}))
        elif count:
            result["count"] = value["result"]["count"]
        else:
            result["health_status"] = value.get("status")
    except Exception as error:
        result["status"] = error.code if isinstance(error, HTTPError) else None
        result["error_type"] = type(error).__name__
    result["duration_ms"] = round((time.monotonic() - started) * 1000, 2)
    return result


def k8s_probe(kind, namespace, resource):
    result = {"read_at": now(), "ok": False}
    args = [str(KUBECTL), "--context=genai", "-n", namespace, "get", *resource, "-o", "json"]
    try:
        output = subprocess.run(args, capture_output=True, text=True, timeout=45, check=True)
        obj = json.loads(output.stdout)
        meta, spec, status = obj.get("metadata", {}), obj.get("spec", {}), obj.get("status", {})
        if kind == "deployment":
            value = {"name": meta.get("name"), "uid": meta.get("uid"),
                     "generation": meta.get("generation"),
                     "observedGeneration": status.get("observedGeneration"),
                     "desired": spec.get("replicas"), "replicas": status.get("replicas", 0),
                     "ready": status.get("readyReplicas", 0),
                     "available": status.get("availableReplicas", 0),
                     "images": [c["image"] for c in spec["template"]["spec"]["containers"]]}
        elif kind == "pods":
            value = []
            for pod in obj["items"]:
                pm, ps = pod["metadata"], pod["status"]
                value.append({"name": pm["name"], "uid": pm["uid"],
                              "node": pod["spec"].get("nodeName"),
                              "deleting": bool(pm.get("deletionTimestamp")),
                              "phase": ps.get("phase"), "podIP": ps.get("podIP"),
                              "ready": any(c["type"] == "Ready" and c["status"] == "True"
                                           for c in ps.get("conditions", [])),
                              "containers": [{"name": c["name"], "image": c["image"],
                                              "imageID": c.get("imageID"), "ready": c["ready"],
                                              "restarts": c["restartCount"],
                                              "state": list(c.get("state", {})),
                                              "last_exit_code": c.get("lastState", {}).get("terminated", {}).get("exitCode"),
                                              "last_reason": c.get("lastState", {}).get("terminated", {}).get("reason")}
                                             for c in ps.get("containerStatuses", [])]})
            value.sort(key=lambda row: row["name"])
        elif kind == "argocd":
            operation = status.get("operationState", {})
            value = {"name": meta.get("name"), "sync": status.get("sync", {}).get("status"),
                     "revision": status.get("sync", {}).get("revision"),
                     "health": status.get("health", {}).get("status"),
                     "operation_phase": operation.get("phase"),
                     "operation_started": operation.get("startedAt"),
                     "operation_finished": operation.get("finishedAt"),
                     "operation_revision": operation.get("syncResult", {}).get("revision"),
                     "target_revision": spec.get("source", {}).get("targetRevision")}
        else:
            value = {"name": meta.get("name"), "type": spec.get("type"),
                     "clusterIP": spec.get("clusterIP"), "ports": spec.get("ports", [])}
        result.update(ok=True, value=value)
    except Exception as error:
        result["error_type"] = type(error).__name__
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--salida", required=True, type=Path)
    parser.add_argument("--comparacion", required=True, type=Path)
    options = parser.parse_args()
    if options.salida.exists() or options.comparacion.exists():
        parser.error("Usa nombres nuevos: no se sobrescribe evidencia anterior.")
    baseline_path = HERE / "baseline-sanitizado.json"
    baseline = json.loads(baseline_path.read_text(encoding="utf-8-sig"))
    snapshot = {"started_at": now(), "mode": "Solo lectura; sin mutaciones de servicios ni datos.",
                "canonical_hash": CANONICAL, "http": {}, "kubernetes": {}}
    endpoints = {f"{name}_{kind}": f"http://localhost:{port}/{route}"
                 for name, port in [("python", 8000), ("java", 8080), ("kubernetes", 8002)]
                 for kind, route in [("health", "health"), ("patients", "patients")]}
    endpoints["qdrant_points"] = "http://localhost:6333/collections/historias/points/count"
    resources = {"deployment": ("genai", ["deployment", "fastapi"]),
                 "pods": ("genai", ["pods", "-l", "app=fastapi"]),
                 "argocd": ("argocd", ["application", "fastapi"]),
                 "service": ("genai", ["service", "fastapi"])}
    with ThreadPoolExecutor(max_workers=11) as executor:
        jobs = [("http", name, executor.submit(http_probe, name, url)) for name, url in endpoints.items()]
        jobs += [("kubernetes", name, executor.submit(k8s_probe, name, ns, resource))
                 for name, (ns, resource) in resources.items()]
        for group, name, future in jobs:
            snapshot[group][name] = future.result()
    snapshot["finished_at"] = now()
    snapshot["patient_hash_matches_python_k8s"] = (
        snapshot["http"]["python_patients"].get("sha256_canonical") is not None and
        snapshot["http"]["python_patients"].get("sha256_canonical") ==
        snapshot["http"]["kubernetes_patients"].get("sha256_canonical"))
    payload = (json.dumps(snapshot, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    with options.salida.open("xb") as output:
        output.write(payload)
    comparisons = {}
    for name in ["python_patients", "java_patients", "kubernetes_patients"]:
        before, after = baseline["http"][name], snapshot["http"][name]
        comparisons[name] = {"before_count": before["count"], "after_count": after.get("count"),
                             "before_sha256": before["sha256_canonical"],
                             "after_sha256": after.get("sha256_canonical"),
                             "unchanged": after.get("status") == 200 and
                             before["count"] == after.get("count") and
                             before["sha256_canonical"] == after.get("sha256_canonical")}
    checks = {"patients_unchanged": all(v["unchanged"] for v in comparisons.values()),
              "python_equals_kubernetes": snapshot["patient_hash_matches_python_k8s"],
              "all_http_200": all(value.get("status") == 200 for value in snapshot["http"].values()),
              "qdrant_count_unchanged_9": baseline["http"]["qdrant_points"]["count"] ==
              snapshot["http"]["qdrant_points"].get("count") == 9,
              "kubernetes_reads_ok": all(value["ok"] for value in snapshot["kubernetes"].values())}
    deployment = snapshot["kubernetes"]["deployment"].get("value", {})
    argo = snapshot["kubernetes"]["argocd"].get("value", {})
    checks["two_replicas_ready"] = deployment.get("desired") == deployment.get("ready") == deployment.get("available") == 2
    checks["argocd_synced_healthy_succeeded"] = (argo.get("sync"), argo.get("health"), argo.get("operation_phase")) == ("Synced", "Healthy", "Succeeded")
    comparison = {"recorded_at": now(), "baseline": baseline_path.name,
                  "baseline_file_sha256": sha(baseline_path.read_bytes()),
                  "final_snapshot": str(options.salida), "final_file_sha256": sha(payload),
                  "canonical_hash": CANONICAL, "patients": comparisons, "checks": checks,
                  "result": "PASS" if all(checks.values()) else "FAIL",
                  "limits": "La igualdad Qdrant solo acredita conteo, no compara payloads ni vectores."}
    with options.comparacion.open("x", encoding="utf-8") as output:
        json.dump(comparison, output, ensure_ascii=False, indent=2)
        output.write("\n")
    print(json.dumps({"result": comparison["result"], "checks": checks,
                      "snapshot": str(options.salida), "comparison": str(options.comparacion)}, ensure_ascii=False))
    return 0 if comparison["result"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
