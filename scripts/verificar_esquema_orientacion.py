"""Paridad offline usando jsonschema real, sin red; --deps permite dependencias locales de pruebas."""
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
from rag import direct_response_schema, rag_response_schema, validate_direct_answer, validate_rag_answer

guide = {"possibilities": [{"cause": "posibilidad A", "condition": "dato A"}],
         "optional_details": ["ubicación", "duración"], "current_alert": None}
cases = []
for question in ("dolor de estómago", "Tengo dolor de estómago"):
    for branch in ("direct", "rag"):
        schema = direct_response_schema(question) if branch == "direct" else rag_response_schema([], question)
        Draft202012Validator.check_schema(schema)
        validator = Draft202012Validator(schema)
        extras = {} if branch == "direct" else {"missing_information": True, "facts": [], "questions": []}
        fixtures = [("orientation", {"mode": "symptom_guidance", "guidance": guide, **extras}, True),
                    ("null_orientation", {"mode": "symptom_guidance", "guidance": None, **extras}, False),
                    ("free_narrative", {"mode": "symptom_guidance", "guidance": "texto libre", **extras}, False)]
        for name, change in (("question", {"optional_details": ["¿Dónde?", "duración"]}),
                             ("control", {"optional_details": ["dato\notro", "duración"]}),
                             ("blank", {"optional_details": ["   ", "duración"]}),
                             ("four_causes", {"possibilities": guide["possibilities"] * 4}),
                             ("non_string", {"possibilities": [{"cause": 42, "condition": "dato"}]})):
            fixtures.append((name, {"mode": "symptom_guidance", "guidance": {**guide, **change}, **extras}, False))
        for name, value, expected in fixtures:
            schema_valid = validator.is_valid(value)
            try:
                raw = json.dumps(value)
                result = validate_direct_answer(raw, question) if branch == "direct" else validate_rag_answer(raw, [], question)
                runtime_valid = isinstance(result, str) and bool(result)
            except ValueError:
                runtime_valid = False
            cases.append({"question": question, "branch": branch, "case": name,
                          "schema_valid": schema_valid, "runtime_valid": runtime_valid,
                          "passed": schema_valid == runtime_valid == expected})
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
