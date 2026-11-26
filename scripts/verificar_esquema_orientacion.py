"""Esquema (jsonschema real) y validación del servidor, offline y sin red; --deps permite dependencias locales de pruebas."""
import argparse
from copy import deepcopy
import json
from pathlib import Path
import sys

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--deps", type=Path)
parser.add_argument("--output", type=Path, required=True)
args = parser.parse_args()
if args.output.exists():
    parser.error("No sobrescribir evidencia")
if args.deps:
    sys.path.insert(0, str(args.deps))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "python-api"))
from jsonschema import Draft202012Validator
from rag import (OUT_OF_SCOPE, direct_response_schema, rag_response_schema, source_label, validate_direct_answer,
                 validate_rag_answer)

guide = {"possibilities": [{"cause": "posibilidad A", "condition": "dato A"}],
         "optional_details": ["ubicación", "duración"], "current_alert": None}
cases = []
for question in ("dolor de estómago", "Tengo dolor de estómago"):
    for branch in ("direct", "rag"):
        schema = direct_response_schema(question) if branch == "direct" else rag_response_schema([], question)
        Draft202012Validator.check_schema(schema)
        validator = Draft202012Validator(schema)
        extras = {} if branch == "direct" else {"missing_information": True, "facts": [], "questions": []}
        # (caso, valor, válido en esquema, válido en servidor). El texto sólo lo valida el servidor:
        # Ollama 0.40 ignora todo el esquema si un texto lleva "pattern".
        fixtures = [("orientation", {"mode": "symptom_guidance", "guidance": guide, **extras}, True, True),
                    ("null_orientation", {"mode": "symptom_guidance", "guidance": None, **extras}, False, False),
                    ("free_narrative", {"mode": "symptom_guidance", "guidance": "texto libre", **extras}, False, False)]
        for name, change, schema_expected, runtime_expected in (
                ("question_detail_shown_as_detail", {"optional_details": ["¿Dónde?", "duración"]}, True, True),
                ("question_cause", {"possibilities": [{"cause": "¿gastritis?", "condition": "dato"}]}, True, False),
                ("control", {"optional_details": ["dato\notro", "duración"]}, True, False),
                ("blank", {"optional_details": ["   ", "duración"]}, True, False),
                ("variable_name", {"optional_details": ["frecuencia_dia", "duración"]}, True, False),
                ("too_long", {"optional_details": ["x" * 121, "duración"]}, True, False),
                ("no_causes", {"possibilities": []}, False, False),
                ("four_causes", {"possibilities": guide["possibilities"] * 4}, False, False),
                ("non_string", {"possibilities": [{"cause": 42, "condition": "dato"}]}, False, False)):
            fixtures.append((name, {"mode": "symptom_guidance", "guidance": {**guide, **change}, **extras},
                             schema_expected, runtime_expected))
        for name, value, schema_expected, runtime_expected in fixtures:
            schema_valid = validator.is_valid(value)
            try:
                raw = json.dumps(value)
                result = validate_direct_answer(raw, question) if branch == "direct" else validate_rag_answer(raw, [], question)
                runtime_valid = isinstance(result, str) and bool(result) and "?" not in result
            except ValueError:
                runtime_valid = False
            cases.append({"question": question, "branch": branch, "case": name,
                          "schema_valid": schema_valid, "runtime_valid": runtime_valid,
                          "passed": schema_valid == schema_expected and runtime_valid == runtime_expected})
        cases.append({"question": question, "branch": branch, "case": "schema_without_text_pattern",
                      "passed": '"pattern"' not in json.dumps(schema) and '"maxLength"' not in json.dumps(schema)})
for branch in ("direct", "rag"):
    question = "Estoy vomitando sangre roja ahora, tengo dolor fuerte en el abdomen y me siento mareada."
    schema = direct_response_schema(question) if branch == "direct" else rag_response_schema([], question)
    extras = {} if branch == "direct" else {"missing_information": True, "facts": [], "questions": []}
    for label, quote, expected in (("alert_literal", question, True),
                                   ("alert_paraphrase_replay", "sangre roja en vómito, dolor abdominal intenso y mareos", False)):
        value = {"mode": "symptom_guidance", "guidance": {**guide, "current_alert": quote}, **extras}
        raw = json.dumps(value)
        try:
            result = validate_direct_answer(raw, question) if branch == "direct" else validate_rag_answer(raw, [], question)
            runtime_valid = bool(result)
        except ValueError:
            runtime_valid = False
        schema_valid = Draft202012Validator(schema).is_valid(value)
        cases.append({"branch": branch, "case": label, "schema_valid": schema_valid,
                      "runtime_valid": runtime_valid, "passed": schema_valid == runtime_valid == expected})
for branch in ("direct", "rag"):
    for label, question, quote, expected in (
            ("negative_final_period", "No estoy vomitando sangre.", "No estoy vomitando sangre.", False),
            ("conditional_final_period", "Si vomitara sangre buscaría ayuda.", "Si vomitara sangre buscaría ayuda.", False),
            ("negative_combined_quote", "No vomito sangre. Estoy cansada.", "No vomito sangre. Estoy cansada.", False),
            ("negative_without_period", "No estoy vomitando sangre", "No estoy vomitando sangre", False),
            ("affirmative_final_period", "Estoy vomitando sangre ahora.", "Estoy vomitando sangre ahora.", True),
            ("affirmative_combined_quote", "Estoy vomitando sangre. Me siento mareada.", "Estoy vomitando sangre. Me siento mareada.", True),
            ("separate_unrelated_negation", "No tengo fiebre. Estoy vomitando sangre.", "Estoy vomitando sangre", True),
            ("inability_is_present", "La paciente no puede respirar y tiene dolor en el pecho",
             "La paciente no puede respirar y tiene dolor en el pecho", True),
            ("affirmative_si", "Si, tiene sangre en el vómito", "Si, tiene sangre en el vómito", True),
            ("negated_presence", "no siente dolor en el pecho pero tiene acidez",
             "no siente dolor en el pecho pero tiene acidez", False),
            ("mixed_clause_conservative_rejection", "Estoy vomitando sangre y no tengo fiebre.", "Estoy vomitando sangre y no tengo fiebre.", False)):
        schema = direct_response_schema(question) if branch == "direct" else rag_response_schema([], question)
        extras = {} if branch == "direct" else {"missing_information": True, "facts": [], "questions": []}
        value = {"mode": "symptom_guidance", "guidance": {**guide, "current_alert": quote}, **extras}
        try:
            raw = json.dumps(value)
            result = validate_direct_answer(raw, question) if branch == "direct" else validate_rag_answer(raw, [], question)
            runtime_valid = bool(result)
        except ValueError:
            runtime_valid = False
        schema_valid = Draft202012Validator(schema).is_valid(value)
        cases.append({"branch": branch, "case": label, "schema_valid": schema_valid,
                      "runtime_valid": runtime_valid, "passed": schema_valid == runtime_valid == expected})
# La orientación cita como máximo un antecedente; la consulta documental, hasta tres.
source = {"source": "paciente-1.md", "record_id": "r1", "section": "Enfermedad", "text": "Ana Demo tiene ERGE."}
fact = {"source": source_label(source), "quote": "Ana Demo tiene ERGE."}
for question, mode, guidance_value, expected in (("dolor de estómago", "symptom_guidance", guide, False),
                                                 ("¿Qué enfermedad consta?", "record_lookup", None, True)):
    value = {"mode": mode, "guidance": guidance_value, "missing_information": False, "facts": [fact, fact], "questions": []}
    schema_valid = Draft202012Validator(rag_response_schema([source], question)).is_valid(value)
    cases.append({"branch": "rag", "case": f"two_facts_{mode}", "schema_valid": schema_valid, "passed": schema_valid == expected})
for question, expected in (("¿Cuál es la capital de Francia?", True), ("dolor de estómago", False)):
    for branch in ("direct", "rag"):
        schema = direct_response_schema(question) if branch == "direct" else rag_response_schema([source], question)
        extras = {} if branch == "direct" else {"missing_information": True, "facts": [], "questions": []}
        raw = json.dumps({"mode": "out_of_scope", "guidance": None, **extras})
        try:
            result = validate_direct_answer(raw, question) if branch == "direct" else validate_rag_answer(raw, [source], question)
            runtime_valid = result == OUT_OF_SCOPE
        except ValueError:
            runtime_valid = False
        schema_valid = Draft202012Validator(schema).is_valid(json.loads(raw))
        cases.append({"question": question, "branch": branch, "case": "out_of_scope", "schema_valid": schema_valid,
                      "runtime_valid": runtime_valid, "passed": schema_valid == runtime_valid == expected})
for branch in ("direct", "rag"):
    question = "¿Qué cirugía está registrada?"
    schema = direct_response_schema(question) if branch == "direct" else rag_response_schema([], question)
    extras = {} if branch == "direct" else {"missing_information": True, "facts": [], "questions": []}
    value = {"mode": "record_lookup", "guidance": None, **extras}
    raw = json.dumps(value)
    result = validate_direct_answer(raw, question) if branch == "direct" else validate_rag_answer(raw, [], question)
    cases.append({"branch": branch, "case": "documentary_missing", "passed": Draft202012Validator(schema).is_valid(value) and bool(result)})
report = {"validator": "jsonschema Draft202012Validator", "scope": __doc__, "cases": cases,
          "passed": all(row["passed"] for row in cases),
          "limits": "La paridad de formato no acredita pertinencia clínica ni que una cita de alarma sea una alarma real; eso se prueba por separado."}
args.output.parent.mkdir(parents=True, exist_ok=True)
args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(json.dumps({"passed": report["passed"], "cases": len(cases)}))
if not report["passed"]:
    raise SystemExit(1)
