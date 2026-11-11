"""Experimento histórico con Qwen3: dos formatos; no cambia la aplicación ni sus datos."""

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
from time import perf_counter

from verificar_hipotesis import (CASES, SOURCES, digest, request_json,
                                  semantic_checks, source_label, validate_rag_answer)
from rag import rag_response_schema

OPTIONS = {"temperature": 0, "num_ctx": 4096, "num_predict": 1024}

SYSTEM = (
    "Eres un asistente de capacitación con pacientes ficticios. Ofrece una hipótesis clínica provisional, "
    "explicada únicamente mediante observaciones del relato actual. La explicación enumera datos, no "
    "mecanismos causales ni hallazgos de pruebas. Incluye una sola alternativa común y razonable, vinculada "
    "a una condición concreta que no se haya afirmado ni negado expresamente. No conviertas la condición "
    "en un síntoma presente. Si no puedes justificar una alternativa, omítela. Responde directamente, "
    "sin preguntas ni indicaciones de medicamentos. Prioriza atención urgente si el relato lo exige. "
    "Usa lenguaje sencillo y un máximo de 120 palabras para la valoración."
)
FORMAT_THREE = (
    "Escribe sólo estas líneas: 'Hipótesis principal: ...', 'A favor: ...' y, si procede, "
    "'Alternativa condicional: si apareciera ... podría tratarse de ...'. "
    "En A favor usa tres datos concretos del relato. No añadas otros apartados."
)
FORMAT_CARD = (
    "Devuelve la ficha JSON solicitada. hipotesis es el nombre de una posibilidad, datos_a_favor "
    "recoge hasta tres observaciones ya relatadas. En alternativa, condicion describe un dato adicional "
    "hipotético y posibilidad nombra qué alternativa apoyaría ese dato. Si no hay alternativa razonable, "
    "usa alternativa=[]. No añadas explicaciones fuera de esos campos."
)


def card_schema(sources):
    properties = {
        "hipotesis": {"type": "string", "maxLength": 180},
        "datos_a_favor": {"type": "array", "maxItems": 3, "items": {"type": "string", "maxLength": 200}},
        "alternativa": {"type": "array", "maxItems": 1, "items": {"type": "object", "properties": {
            "condicion": {"type": "string", "maxLength": 180}, "posibilidad": {"type": "string", "maxLength": 180}},
            "required": ["condicion", "posibilidad"], "additionalProperties": False}},
    }
    if sources:
        properties["antecedentes"] = {"type": "array", "maxItems": 1, "items": {"type": "object", "properties": {
            "source": {"type": "string", "enum": [source_label(s) for s in sources]}, "quote": {"type": "string"}},
            "required": ["source", "quote"], "additionalProperties": False}}
    return {"type": "object", "properties": properties, "required": list(properties), "additionalProperties": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(args.output)
    case = next(c for c in CASES if c["id"] == "relato_2")
    report = {"started_at": datetime.now(timezone.utc).isoformat(), "scope": __doc__, "model": "qwen3:4b-instruct-2507-q4_K_M",
              "options": OPTIONS, "case": case, "system": SYSTEM, "verifier_sha256": digest(Path(__file__).read_bytes()),
              "clinical_acceptance": "pending_manual_review", "results": []}
    args.output.parent.mkdir(parents=True, exist_ok=True)

    def save():
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    for candidate in ("tres_lineas", "ficha"):
        for branch in ("direct", "rag"):
            sources = SOURCES if branch == "rag" else []
            context = "\n\n".join(source_label(s) + "\n" + s["text"] for s in sources)
            instruction = FORMAT_THREE if candidate == "tres_lineas" else FORMAT_CARD
            if branch == "rag":
                instruction += (" El historial sólo sirve como antecedente; la hipótesis y su explicación deben "
                                "responder al relato actual. Cita a lo sumo un antecedente pertinente, copiando su "
                                "texto literalmente con la etiqueta proporcionada, después de la valoración.")
            if candidate == "tres_lineas" and branch == "rag":
                instruction += (" Usa mode=symptom_guidance, escribe esas tres líneas en guidance; facts contiene "
                                "las citas o []; missing_information=true si no consta una causa confirmada; questions=[].")
            prompt = instruction + ("\n\nANTECEDENTES:\n" + context if context else "") + "\n\nRELATO ACTUAL:\n" + case["question"]
            body = {"model": report["model"], "system": SYSTEM, "prompt": prompt, "options": OPTIONS, "stream": False, "keep_alive": "1m"}
            if candidate == "ficha":
                body["format"] = card_schema(sources)
            elif branch == "rag":
                body["format"] = rag_response_schema(sources)
            started = perf_counter()
            row = {"candidate": candidate, "branch": branch, "prompt": prompt, "schema": body.get("format")}
            try:
                result = request_json("POST", "http://localhost:11434/api/generate", body, timeout=180)
                raw = result["response"]
                if candidate == "ficha":
                    parsed = json.loads(raw)
                    guidance = "Hipótesis principal: " + parsed["hipotesis"] + "\nA favor: " + "; ".join(parsed["datos_a_favor"])
                    guidance += "".join("\nAlternativa condicional: si " + alt["condicion"] + ", podría ser " + alt["posibilidad"] for alt in parsed["alternativa"])
                    normalized = json.dumps({"mode": "symptom_guidance", "missing_information": True, "guidance": guidance,
                                             "facts": parsed.get("antecedentes", []), "questions": []}, ensure_ascii=False)
                    answer = guidance if branch == "direct" else validate_rag_answer(normalized, sources, case["question"])
                else:
                    normalized = raw
                    answer = raw.strip() if branch == "direct" else validate_rag_answer(raw, sources, case["question"])
                checks = semantic_checks(case, answer, branch, normalized if branch == "rag" else None)
                checks["generation_complete"] = result.get("done") is True and result.get("done_reason") != "length"
                row.update(raw=raw, answer=answer, checks=checks, automatic_passed=all(checks.values()))
            except Exception as error:
                row.update(error=str(error), automatic_passed=False)
            row["seconds"] = round(perf_counter() - started, 3)
            report["results"].append(row)
            save()
            print(json.dumps({"candidate": candidate, "branch": branch, "automatic_passed": row["automatic_passed"], "seconds": row["seconds"]}), flush=True)
    report["finished_at"] = datetime.now(timezone.utc).isoformat()
    save()


if __name__ == "__main__":
    main()
