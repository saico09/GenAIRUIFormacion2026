"""Comparación real en lectura, sin /chat ni persistencia; por defecto sólo muestra el plan."""
import argparse
import ast
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from threading import Event, Thread
from time import perf_counter
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
os.environ["HISTORY_AUTO_SYNC"] = "false"
sys.path.insert(0, str(ROOT / "python-api"))
from app.knowledge import COLLECTION, search_fragments
from rag import (DIRECT_SYSTEM, RAG_SYSTEM, SYMPTOM_GUIDANCE, build_rag_prompt, direct_response_schema,
                 rag_response_schema, validate_direct_answer, validate_rag_answer)

CASES = {"agudo": "dolor de estómago agudo", "estomago": "dolor de estómago",
         "cabeza": "dolor de cabeza", "vago": "me siento mal"}


def http(url, body=None, timeout=15):
    request = Request(url, data=None if body is None else json.dumps(body, ensure_ascii=False).encode(),
                      headers={"Content-Type": "application/json"})
    with urlopen(request, timeout=timeout) as response:
        return json.load(response)


def configuration():
    values = {}
    for node in ast.parse((ROOT / "python-api/app/llm.py").read_text(encoding="utf-8")).body:
        if not isinstance(node, ast.Assign) or len(node.targets) != 1 or not isinstance(node.targets[0], ast.Name):
            continue
        name = node.targets[0].id
        if name == "CHAT_MODEL":
            values[name] = os.getenv("CHAT_MODEL", ast.literal_eval(node.value.args[1]))
        elif name == "MODEL_OPTIONS":
            values[name] = {ast.literal_eval(k): values[v.id] if isinstance(v, ast.Name) else ast.literal_eval(v)
                            for k, v in zip(node.value.keys, node.value.values)}
        elif name in {"TEMPERATURE", "THINK", "TIMEOUT_SECONDS"}:
            values[name] = ast.literal_eval(node.value)
    return values


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def markdown_hashes():
    return {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in (ROOT / "datos/historias").glob("*.md")}


def index_snapshot():
    points, offset = [], None
    while True:
        body = {"limit": 100, "with_payload": True, "with_vector": True}
        if offset is not None:
            body["offset"] = offset
        data = http(f"http://localhost:6333/collections/{COLLECTION}/points/scroll", body)["result"]
        points.extend(data["points"])
        offset = data["next_page_offset"]
        if offset is None:
            return {"count": len(points), "sha256": digest(sorted(points, key=lambda row: str(row["id"])))}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--cases", default="agudo", help="agudo,estomago,cabeza,vago; por defecto sólo agudo")
    parser.add_argument("--patient-id", type=int, default=1)
    parser.add_argument("--model", help="Modelo sólo para este experimento; no cambia la aplicación")
    parser.add_argument("--temperature", type=float, help="Temperatura sólo para este experimento")
    parser.add_argument("--policy-file", type=Path, help="Sustituye sólo la política compartida durante el experimento")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    selected = args.cases.split(",")
    if not selected or len(selected) != len(set(selected)) or not set(selected) <= CASES.keys():
        parser.error("Selección de casos inválida")
    config = configuration()
    if args.model:
        config["CHAT_MODEL"] = args.model
    if args.temperature is not None:
        if not 0 <= args.temperature <= 2:
            parser.error("La temperatura experimental debe estar entre0 y2")
        config["TEMPERATURE"] = config["MODEL_OPTIONS"]["temperature"] = args.temperature
    systems = {"rag": RAG_SYSTEM, "direct": DIRECT_SYSTEM}
    policy = None
    if args.policy_file:
        policy = args.policy_file.read_text(encoding="utf-8").strip()
        if not policy:
            parser.error("La política experimental no puede estar vacía")
        systems = {branch: system.replace(SYMPTOM_GUIDANCE, policy + "\n", 1) for branch, system in systems.items()}
    plan = {"cases": {name: CASES[name] for name in selected}, "configuration": config, "model_override": args.model,
            "temperature_override": args.temperature, "experimental_policy": policy,
            "experimental_policy_sha256": hashlib.sha256(policy.encode()).hexdigest() if policy else None,
            "order": ["retrieval", "rag", "direct"], "llm_calls": 2 * len(selected), "patient_id": args.patient_id}
    if not args.execute:
        print(json.dumps(plan, ensure_ascii=False, indent=2))
        return
    if args.output is None or args.output.exists():
        parser.error("Usa --output con un archivo nuevo")
    base = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/")
    model_metadata = http(base + "/api/show", {"model": config["CHAT_MODEL"]})
    patient = http(f"http://localhost:8080/patients/{args.patient_id}")
    before_md, before_index = markdown_hashes(), index_snapshot()
    report = {"started_at": datetime.now(timezone.utc).isoformat(), "scope": __doc__, **plan,
              "manual_semantic_review_required": True, "systems_sent": systems,
              "generation_endpoint": base + "/api/generate", "source_sha256": {
                  name: hashlib.sha256((ROOT / "python-api" / name).read_bytes()).hexdigest()
                  for name in ("rag.py", "app/llm.py", "app/main.py")},
              "loaded_models_before": http(base + "/api/ps"), "index_before": before_index,
              "model_metadata": {key: model_metadata.get(key) for key in ("details", "capabilities", "thinking", "parameters")},
              "model_template_sha256": hashlib.sha256(model_metadata.get("template", "").encode()).hexdigest(),
              "cases_results": [], "resource_samples": [], "checks": {}, "technical_passed": False}
    args.output.parent.mkdir(parents=True, exist_ok=True)

    def save():
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    phase, stop = {"value": "before_retrieval"}, Event()

    def monitor():
        while not stop.is_set():
            sample = {"at": datetime.now(timezone.utc).isoformat(), "phase": phase["value"]}
            try:
                sample["ollama_ps"] = http(base + "/api/ps", timeout=3)
            except Exception as error:
                sample["ps_error"] = type(error).__name__
            try:
                gpu = subprocess.run(["nvidia-smi", "--query-gpu=memory.total,memory.used,utilization.gpu,utilization.memory",
                                      "--format=csv,noheader,nounits"], capture_output=True, text=True, timeout=3)
                sample["gpu_csv"] = gpu.stdout.strip()
                sample["gpu_exit_code"] = gpu.returncode
            except Exception as error:
                sample["gpu_error"] = type(error).__name__
            report["resource_samples"].append(sample)
            stop.wait(5)

    watcher = Thread(target=monitor, daemon=True)
    save()
    watcher.start()
    try:
        for name in selected:
            question = CASES[name]
            phase["value"] = name + ":retrieval"
            started = perf_counter()
            sources = search_fragments(args.patient_id, question)
            retrieval_seconds = round(perf_counter() - started, 3)
            for branch in ("rag", "direct"):
                phase["value"] = name + ":" + branch
                prompt = build_rag_prompt(question, sources, patient["name"]) if branch == "rag" else question
                body = {"model": config["CHAT_MODEL"], "prompt": prompt, "stream": False,
                        "system": systems[branch],
                        "think": config["THINK"], "options": dict(config["MODEL_OPTIONS"]), "keep_alive": "1m"}
                if branch == "rag":
                    body["format"] = rag_response_schema(sources, question)
                else:
                    body["format"] = direct_response_schema(question)
                started = perf_counter()
                raw = http(base + "/api/generate", body, timeout=config["TIMEOUT_SECONDS"])
                row = {"case": name, "question": question, "branch": branch,
                       "request_sha256": digest(body),
                       "elapsed_seconds": round(perf_counter() - started, 3), "retrieval_seconds": retrieval_seconds,
                       "thinking_returned": bool(raw.get("thinking")), "done_reason": raw.get("done_reason"),
                       "metrics": {key: raw.get(key) for key in ("total_duration", "load_duration", "prompt_eval_duration",
                                   "eval_duration", "prompt_eval_count", "prompt_eval_cached_count", "eval_count")}}
                complete = raw.get("done") is True and raw.get("done_reason") != "length" and bool(raw.get("response", "").strip())
                row["complete"] = complete
                if complete:
                    row["raw_final_response"] = raw["response"]
                    row["sources"] = sources if branch == "rag" else []
                report["cases_results"].append(row)
                save()
                if complete:
                    try:
                        row["answer"] = validate_rag_answer(raw["response"], sources, question) if branch == "rag" else validate_direct_answer(raw["response"], question)
                        row["validated"] = True
                        row["no_questions"] = "?" not in row["answer"]
                    except ValueError as error:
                        row["validated"] = False
                        row["validation_error"] = str(error)
                        save()
                        raise
                    save()
                print(json.dumps({"case": name, "branch": branch, "complete": complete, "seconds": row["elapsed_seconds"]}), flush=True)
                if not complete:
                    raise RuntimeError("Respuesta incompleta; se conserva sólo metadata, sin mostrar texto parcial")
        report["technical_passed"] = True
    except BaseException as error:
        report["error"] = str(error)
        raise
    finally:
        stop.set()
        watcher.join(timeout=10)
        report["index_after"] = index_snapshot()
        report["checks"] = {"markdown_unchanged": before_md == markdown_hashes(),
                            "qdrant_unchanged": before_index == report["index_after"]}
        report["technical_passed"] = report["technical_passed"] and all(report["checks"].values())
        report["finished_at"] = datetime.now(timezone.utc).isoformat()
        save()


if __name__ == "__main__":
    main()
