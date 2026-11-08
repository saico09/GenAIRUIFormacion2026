"""Contratos offline: formato compartido, validación y compensación de archivos propios."""

from contextlib import contextmanager
from datetime import datetime, timezone
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
from uuid import uuid4

from fastapi import HTTPException
from pydantic import ValidationError

from app import clinical_store as store
from app.history_documents import parse_history
from app.models import Patient
from app.observability import transaction_patient_id
from app.schemas import DiseaseIn, PatientIn

checks = []


def case(name, action):
    action()
    checks.append(name)


def expect_invalid(action):
    try:
        action()
    except (ValidationError, HTTPException):
        return
    raise AssertionError("Se admitió un valor inválido")


def equal(actual, expected):
    assert actual == expected, (actual, expected)


case("campos_vacios", lambda: expect_invalid(lambda: DiseaseIn(disease="", treatment=" ", medication="No registrado.")))
case("control_en_campo", lambda: expect_invalid(lambda: DiseaseIn(disease="dolor\x00", treatment="", medication="")))
case("encabezado_en_campo", lambda: expect_invalid(lambda: DiseaseIn(disease="x\n### Consulta", treatment="", medication="")))
case("limite_utf16", lambda: expect_invalid(lambda: DiseaseIn(disease="😀" * 1001, treatment="", medication="")))
case("nombre_invalido", lambda: expect_invalid(lambda: PatientIn(name="Ana\nDemo", birth_date="2000-01-01", email="a@example.com")))
case("normalizar_campo", lambda: equal(DiseaseIn(disease="  Dolor\r\nleve ", treatment="No registrado.", medication="").model_dump(),
                                       {"disease": "Dolor\nleve", "treatment": "", "medication": ""}))
patient = Patient(id=12, name="Ána Prueba", birth_date=datetime(2000, 1, 1).date(), email="test@example.com")
entry = {"id": str(uuid4()), "disease": "Rinitis alérgica", "treatment": "Evitar polen", "medication": ""}
case("nombre_representativo", lambda: equal(store.filename(patient).name, "paciente-12-ana-prueba.md"))
case("render_parse_sin_diario", lambda: equal(parse_history(store.render(patient, [entry], ""), store.filename(patient).name)["entries"], [entry]))


class JournalSession:
    def scalars(self, query):
        return self

    def all(self):
        return [SimpleNamespace(id="00000000-0000-0000-0000-000000000001", model="modelo", question="Primera\nSegunda",
                                direct_answer="Respuesta 1", rag_answer="Respuesta 2",
                                created_at=datetime(2026, 11, 7, 12, 0, 0, 123000, tzinfo=timezone.utc))]


journal = store.render_journal(JournalSession(), 12)
case("instant_compatible_java", lambda: equal("Fecha UTC: 2026-11-07T12:00:00.123Z" in journal, True))
case("notas_journal", lambda: equal(parse_history(store.render(patient, [entry], journal), store.filename(patient).name)["consultations"][0]["question"], "Primera\nSegunda"))


class TransactionSession:
    bind = None
    invalidated = False

    def get_bind(self):
        return self

    @contextmanager
    def connect(self):
        yield self

    @contextmanager
    def begin(self):
        yield

    def execute(self, statement, *args):
        if "pg_advisory_unlock" in str(statement):
            assert file.read_text() == "original"

    def commit(self):
        pass

    def flush(self):
        pass


with tempfile.TemporaryDirectory() as directory:
    original_directory = store.DIRECTORY
    store.DIRECTORY = Path(directory)
    file = Path(directory) / "paciente-12-ana-prueba.md"
    file.write_text("original")
    def rollback():
        try:
            with store.clinical_transaction(TransactionSession()) as changes:
                changes.write(file, "cambio")
                changes.write(Path(directory) / "nuevo.md", "nuevo")
                raise ValueError("simulado")
        except ValueError:
            pass
        assert file.read_text() == "original"
        assert not (Path(directory) / "nuevo.md").exists()
    case("compensacion_antes_unlock", rollback)
    class CommitFailureSession(TransactionSession):
        @contextmanager
        def begin(self):
            yield
            raise RuntimeError("commit simulado")

    def commit_failure():
        try:
            with store.clinical_transaction(CommitFailureSession()) as changes:
                changes.write(file, "no confirmado")
        except RuntimeError:
            pass
        assert file.read_text() == "original"
    case("compensacion_commit_antes_unlock", commit_failure)
    case("archivo_unico", lambda: equal(store.find_file(12), file))
    (Path(directory) / "paciente-12-duplicado.md").write_text("conflicto")
    case("duplicado_no_sobrescribe", lambda: expect_invalid(lambda: store.find_file(12)))
    store.DIRECTORY = original_directory

for path, method, status, incoming, outgoing, expected in [
    ("/patients/4/diseases/abc", "DELETE", 404, "", "", 4),
    ("/clinical/patients/24/sync", "POST", 200, "", "", 24),
    ("/patients", "POST", 201, "{}", '{"id":24}', 24),
    ("/patients", "POST", 422, "{}", '{"id":24}', None),
    ("/chat", "POST", 503, '{"patient_id":4}', "", 4),
    ("/chat", "POST", 422, '{"patient_id":true}', "", None),
    ("/patients/9999999999999", "GET", 404, "", "", None),
    ("/clinical/proposals", "POST", 422, "{mal", "", None),
]:
    case(f"auditoria_{len(checks)}", lambda: equal(transaction_patient_id(path, method, status, incoming, outgoing), expected))

print(json.dumps({"result": "PASS", "checks": checks, "count": len(checks)}, ensure_ascii=False))
