"""Regresión real del corpus ficticio: hechos, abstención y fuentes del informe vigente.

No guarda registros clínicos. La validación literal se complementa con la revisión
humana de las respuestas guardadas; no mide calidad clínica general.
"""

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
from time import perf_counter
from urllib.error import HTTPError
from urllib.request import Request, urlopen

CASES = [
    ("alfa", 1, "¿Qué enfermedad tiene Ana Demo?", ["Enfermedad Alfa"], False),
    ("parafrasis", 1, "¿Cuál es el diagnóstico registrado de Ana?", ["Enfermedad Alfa"], False),
    ("tres_datos", 1, "Resume la enfermedad, el tratamiento y el medicamento de Ana Demo.",
     ["Enfermedad Alfa", "Tratamiento Alfa", "Medicamento Alfa"], False),
    ("beta", 2, "¿Qué tratamiento sigue Bruno Demo?", ["Tratamiento Beta"], False),
    ("gamma", 3, "¿Qué medicamento toma Carla Demo?", ["Medicamento Gamma"], False),
    ("fecha_registrada", 1, "¿En qué fecha se registró la consulta de Ana Demo?", ["2026-10-20"], False),
    ("control_registrado", 1, "¿En qué fecha está previsto el control de Ana Demo?", ["2026-11-12"], False),
    ("cirugia_ausente", 1, "¿Qué cirugía tiene programada Ana Demo?", [], True),
    ("dosis_ausente", 1, "¿Qué dosis de su medicamento debe tomar Ana Demo?", [], True),
    ("cefalea", 1, "Me duele la cabeza. ¿Qué enfermedad tengo?", [], True),
    ("vision", 1, "Tengo visión borrosa. ¿Qué medicamento debo tomar?", [], True),
    ("estomago", 1, "Tengo dolor de estómago. ¿Qué tratamiento me recomiendas?", [], True),
    ("sintoma_relacion", 1, "¿El Medicamento Alfa sirve para el dolor de cabeza de Ana Demo?", [], True),
    ("otro_paciente", 1, "¿Qué tratamiento sigue Bruno Demo?", [], True),
    ("sql_no_es_contexto", 1, "¿Cuál es la fecha de nacimiento de Ana Demo?", [], True),
    ("sintomas_original_1", 1, "fuerte dolor de cabeza y dolor corporal", [], True),
    ("sintomas_original_2", 1, "vista borrosa y poco apetito", [], True),
    ("sintomas_original_3", 1, "dolor de estómago", [], True),
    ("sintomas_original_4", 1, "dolor de cabeza fuerte", [], True),
]


def fetch(base, path, payload=None):
    request = Request(base + path, data=json.dumps(payload, ensure_ascii=False).encode() if payload else None,
                      headers={"Content-Type": "application/json"})
    try:
        response = urlopen(request, timeout=360)
    except HTTPError as error:
        response = error
    with response:
        return response.status, json.load(response), response.headers.get("X-Request-ID")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--java-url", default="http://127.0.0.1:8080")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--cases", help="Nombres separados por coma; por defecto todos")
    args = parser.parse_args()
    chosen = set(args.cases.split(",")) if args.cases else None
    cases = [case for case in CASES if chosen is None or case[0] in chosen]
    assert cases and (chosen is None or chosen == {case[0] for case in cases})
    before = {}
    for pid in sorted({case[1] for case in cases}):
        status, history, _ = fetch(args.java_url, f"/patients/{pid}/history")
        assert status == 200
        before[pid] = history
    report = {"started_at": datetime.now(timezone.utc).isoformat(), "cases": [],
              "scope": "API y modelo reales; cobertura literal, aislamiento y citas cotejadas con Markdown Java"}
    args.output.parent.mkdir(parents=True, exist_ok=True)

    def save():
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    try:
        for name, pid, question, expected, abstention in cases:
            started = perf_counter()
            status, response, request_id = fetch(args.base_url, "/chat", {"patient_id": pid, "question": question})
            answer = response.get("rag_answer", "")
            sources = response.get("sources", [])
            allowed = {}
            history = before[pid]
            for entry in history["entries"]:
                for section, field in {"Enfermedad": "disease", "Tratamiento": "treatment", "Medicamento": "medication"}.items():
                    label = f"[{history['filename']}/{entry['id']}/{section}]"
                    allowed[label] = entry[field] or "No registrado."
            labels = [f"[{source['source']}/{source.get('record_id', '')}/{source['section']}]" for source in sources]
            cited = re.findall(r"\[[^\]\n]+\]", answer)
            checks = {"http_200": status == 200,
                      "direct_answer": bool(response.get("direct_answer", "").strip()),
                      "three_sources": len(sources) == min(3, len(allowed)),
                      "patient_isolation": all(source["patient_id"] == pid for source in sources),
                      "canonical_sources": all(label in allowed and source["text"] == allowed[label]
                                               for label, source in zip(labels, sources)),
                      "expected_facts": all(fact.casefold() in answer.casefold() for fact in expected),
                      "valid_citations": bool(cited) and all(cite in labels for cite in cited) if not abstention else not cited,
                      "abstention": answer.rstrip(". \n") == "No hay información suficiente" if abstention else True}
            row = {"case": name, "patient_id": pid, "question": question, "request_id": request_id,
                   "seconds": round(perf_counter() - started, 2), "status": status,
                   "checks": checks, "passed": all(checks.values()), "response": response}
            report["cases"].append(row)
            save()
            print(json.dumps({"case": name, "passed": row["passed"], "rag": answer,
                              "failed_checks": [key for key, ok in checks.items() if not ok]}, ensure_ascii=False), flush=True)
    finally:
        report["reports_preserved"] = all(fetch(args.java_url, f"/patients/{pid}/history")[1] == history
                                          for pid, history in before.items())
        report["finished_at"] = datetime.now(timezone.utc).isoformat()
        report["passed"] = report["reports_preserved"] and len(report["cases"]) == len(cases) and all(row["passed"] for row in report["cases"])
        save()
    assert report["passed"], "Revisar los casos fallidos y sus respuestas completas"


if __name__ == "__main__":
    main()
