"""Ensayo real de recuperación y RAG sin añadir consultas al diario.

Usa Qdrant y Ollama existentes, más el prompt/validador del código local. No llama
a /chat, no sincroniza el índice y no escribe Markdown ni consultas SQL. Los GET
de Java quedan en su auditoría HTTP normal. No acredita el recorrido de la UI ni
exactitud clínica general; verifica hechos concretos del corpus de capacitación.
"""

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import sys
from time import perf_counter

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python-api"))
# Una prueba de lectura nunca debe activar sync_history como efecto secundario.
os.environ["HISTORY_AUTO_SYNC"] = "false"
from app.history_documents import fragments_from_history, parse_history
from app.knowledge import COLLECTION, OLLAMA_BASE_URL, qdrant, request_json, search_fragments
from rag import RAG_SYSTEM, build_rag_prompt, rag_response_schema, source_label, validate_rag_answer


CASES = [
    ("ana_enfermedad", 1, "¿Qué enfermedad tiene Ana Demo?", ["reflujo gastroesofágico"]),
    ("ana_plan", 1, "¿Qué tratamiento tiene registrado Ana Demo?", ["tres horas entre la cena y acostarse"]),
    ("ana_medicamento", 1, "¿Qué medicamento recibe Ana Demo?", ["omeprazol"]),
    ("ana_dosis_ausente", 1, "¿Qué dosis de omeprazol tiene registrada Ana Demo?", []),
    ("ana_cirugia_ausente", 1, "¿Qué cirugía tiene registrada Ana Demo?", []),
    ("bruno_enfermedad", 2, "¿Qué enfermedad tiene Bruno Demo?", ["diabetes mellitus tipo 2"]),
    ("bruno_plan", 2, "¿Qué tratamiento sigue Bruno Demo?", ["plan de alimentación"]),
    ("bruno_medicamento", 2, "¿Qué medicamento recibe Bruno Demo?", ["metformina"]),
    ("carla_enfermedad", 3, "¿Qué enfermedad tiene Carla Demo?", ["rinitis alérgica estacional"]),
    ("carla_plan", 3, "¿Qué tratamiento tiene registrado Carla Demo?", ["lavados nasales"]),
    ("carla_medicamento", 3, "¿Qué medicamento recibe Carla Demo?", ["cetirizina"]),
    ("carla_alergia_ambiental", 3, "¿A qué alérgeno ambiental tiene alergia Carla Demo según su informe?", ["polen"]),
    ("carla_alergia_medicamentos_ausente", 3, "¿Qué alergias a medicamentos tiene documentadas Carla Demo?", []),
    ("otro_paciente", 1, "¿Qué tratamiento sigue Bruno Demo?", []),
]


def digest(value):
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(raw).hexdigest()


def vector_snapshot():
    points, offset = [], None
    while True:
        body = {"limit": 100, "with_payload": True, "with_vector": True}
        if offset is not None:
            body["offset"] = offset
        result = qdrant("POST", f"/collections/{COLLECTION}/points/scroll", body)["result"]
        points.extend(result["points"])
        offset = result.get("next_page_offset")
        if offset is None:
            return {"count": len(points), "sha256": digest(sorted(points, key=lambda p: str(p["id"])))}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--java-url", default="http://127.0.0.1:8080")
    parser.add_argument("--model", default="qwen3:4b-instruct-2507-q4_K_M")
    parser.add_argument("--cases", help="Nombres separados por coma; por defecto los catorce casos")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("La evidencia ya existe; usa otro nombre para conservar el ensayo anterior")
    selected = set(args.cases.split(",")) if args.cases else {c[0] for c in CASES}
    cases = [case for case in CASES if case[0] in selected]
    if not cases or selected != {case[0] for case in cases}:
        parser.error("Nombre de caso desconocido")
    corpus = json.loads((ROOT / "datos/casos_clinicos.json").read_text(encoding="utf-8"))
    definitions = {row["patient_id"]: row for row in corpus["cases"]}

    def histories():
        return {pid: request_json("GET", f"{args.java_url}/patients/{pid}/history", timeout=15)
                for pid in sorted(definitions)}

    before = histories()
    allowed = {}
    for pid, history in before.items():
        definition = definitions[pid]
        record = next(e for e in history["entries"] if e["id"] == definition["record_id"])
        assert all(record[field] == definition[field] for field in ("disease", "treatment", "medication")), "Actualizar primero el corpus demo de Java"
        parsed = parse_history(history["markdown"], history["filename"])
        allowed[pid] = {source_label(p["payload"]): p["payload"]["text"] for p in fragments_from_history(parsed)}
    report = {"started_at": datetime.now(timezone.utc).isoformat(), "scope": __doc__,
              "corpus_version": corpus["version"], "model": args.model,
              "options": {"temperature": 0, "num_ctx": 4096, "num_predict": 1024},
              "qdrant_before": vector_snapshot(), "cases": [], "passed": False}
    args.output.parent.mkdir(parents=True, exist_ok=True)

    def save():
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    save()
    try:
        for name, pid, question, expected in cases:
            started = perf_counter()
            row = {"case": name, "patient_id": pid, "question": question, "expected_facts": expected}
            try:
                sources = search_fragments(pid, question)
                raw = request_json("POST", f"{OLLAMA_BASE_URL}/api/generate", {
                    "model": args.model, "system": RAG_SYSTEM,
                    "prompt": build_rag_prompt(question, sources, definitions[pid]["name"]),
                    "format": rag_response_schema(sources), "options": report["options"],
                    "stream": False, "keep_alive": "1m"}, timeout=180)
                answer = validate_rag_answer(raw["response"], sources, question)
                labels = [source_label(s) for s in sources]
                citations = re.findall(r"\[[^\]\n]+\]", answer)
                absent = not expected
                checks = {"generation_completed": raw.get("done") is True and raw.get("done_reason") != "length",
                          "three_sources": len(sources) == 3,
                          "patient_isolation": all(s["patient_id"] == pid for s in sources),
                          "exact_current_sources": all(allowed[pid].get(source_label(s)) == s["text"] for s in sources),
                          "expected_facts": all(term.casefold() in answer.casefold() for term in expected),
                          "valid_citations": not citations if absent else bool(citations) and all(c in labels for c in citations),
                          "missing_data_not_invented": answer.rstrip(". \n") == "No hay información suficiente" if absent else True}
                row.update(raw=raw["response"], response={"rag_answer": answer, "sources": sources},
                           checks=checks, passed=all(checks.values()))
            except Exception as error:
                row.update(error=str(error), passed=False)
            row["seconds"] = round(perf_counter() - started, 3)
            report["cases"].append(row)
            save()
            print(json.dumps({"case": name, "passed": row["passed"], "seconds": row["seconds"],
                              "failed_checks": [k for k, v in row.get("checks", {}).items() if not v]}, ensure_ascii=False), flush=True)
    finally:
        after = histories()
        report["histories_before_sha256"] = {pid: digest(h) for pid, h in before.items()}
        report["histories_after_sha256"] = {pid: digest(h) for pid, h in after.items()}
        report["histories_and_consultations_unchanged"] = before == after
        report["qdrant_after"] = vector_snapshot()
        report["qdrant_unchanged"] = report["qdrant_after"] == report["qdrant_before"]
        report["finished_at"] = datetime.now(timezone.utc).isoformat()
        report["passed"] = (len(report["cases"]) == len(cases) and all(c["passed"] for c in report["cases"])
                            and report["histories_and_consultations_unchanged"] and report["qdrant_unchanged"])
        save()
    assert report["passed"], "Revisar evidencia: falló un caso o cambió el estado observado"


if __name__ == "__main__":
    main()
