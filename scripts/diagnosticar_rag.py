"""Experimento de lectura sobre /chat; no modifica pacientes ni documentos.

Guarda respuestas completas y cobertura literal de datos ficticios. La cobertura
no es una evaluación clínica ni demuestra corrección semántica por sí sola.
"""

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from time import perf_counter
from urllib.error import HTTPError
from urllib.request import Request, urlopen


CASES = [
    ("literal", "¿Qué enfermedad tiene Ana Demo?", ["Enfermedad Alfa"]),
    ("parafrasis", "¿Cuál es el diagnóstico de Ana?", ["Enfermedad Alfa"]),
    ("tratamiento", "¿Cómo se está tratando a Ana Demo?", ["Tratamiento Alfa"]),
    ("sin_nombre", "¿Qué medicamento toma?", ["Medicamento Alfa"]),
    ("tres_datos", "Resume la enfermedad, el tratamiento y el medicamento de Ana Demo.",
     ["Enfermedad Alfa", "Tratamiento Alfa", "Medicamento Alfa"]),
    ("resumen", "Cuéntame la historia clínica de Ana Demo.",
     ["Enfermedad Alfa", "Tratamiento Alfa", "Medicamento Alfa"]),
    ("dosis_ausente", "¿Qué dosis de su medicamento debe tomar Ana Demo?", []),
    ("consulta_ausente", "¿Cuándo fue la última consulta médica de Ana Demo?", []),
    ("dato_solo_sql", "¿Cuál es la fecha de nacimiento de Ana Demo?", []),
    ("otro_paciente", "¿Qué tratamiento sigue Bruno Demo?", []),
    ("pregunta_corta", "¿Qué tiene?", ["Enfermedad Alfa"]),
    ("control_repetido", "¿Qué enfermedad tiene Ana Demo?", ["Enfermedad Alfa"]),
]


def fetch(base, path, payload=None):
    request = Request(base + path,
                      data=json.dumps(payload, ensure_ascii=False).encode() if payload else None,
                      headers={"Content-Type": "application/json"})
    try:
        response = urlopen(request, timeout=360)
    except HTTPError as failure:
        response = failure
    with response:
        return response.status, json.load(response), response.headers.get("X-Request-ID")


def fingerprint(rows):
    canonical = json.dumps(sorted(rows, key=lambda row: row["id"]),
                           ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return {"count": len(rows), "sha256": hashlib.sha256(canonical.encode()).hexdigest()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    status, rows, _ = fetch(args.base_url, "/patients")
    assert status == 200
    report = {"started_at": datetime.now(timezone.utc).isoformat(),
              "patient_id": 1, "before": fingerprint(rows), "cases": [],
              "evaluation": "Cobertura literal orientativa; revisar respuestas y fuentes manualmente."}

    def save():
        output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    try:
        for label, question, expected in CASES:
            started = perf_counter()
            status, result, request_id = fetch(args.base_url, "/chat", {"patient_id": 1, "question": question})
            answer = result.get("rag_answer", "")
            sources = result.get("sources", [])
            source_text = "\n".join(source["text"] for source in sources)
            row = {"case": label, "question": question, "status": status,
                   "seconds": round(perf_counter() - started, 2), "request_id": request_id,
                   "expected_known_facts": expected,
                   "facts_retrieved": [fact for fact in expected if fact.casefold() in source_text.casefold()],
                   "facts_answered": [fact for fact in expected if fact.casefold() in answer.casefold()],
                   "abstention": "no hay información suficiente" in answer.casefold(),
                   "response": result}
            report["cases"].append(row)
            save()
            print(json.dumps({"case": label, "http": status, "rag": answer,
                              "sections": [source["section"] for source in sources]}, ensure_ascii=False), flush=True)
    finally:
        status, rows, _ = fetch(args.base_url, "/patients")
        report["after"] = fingerprint(rows)
        report["patients_preserved"] = report["after"] == report["before"]
        report["finished_at"] = datetime.now(timezone.utc).isoformat()
        save()
    assert status == 200 and report["patients_preserved"]


if __name__ == "__main__":
    main()
