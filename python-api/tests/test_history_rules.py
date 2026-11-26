"""Reglas del Markdown, recuperación y bloqueo sin PostgreSQL: respaldos en memoria y carpeta temporal."""

from contextlib import contextmanager
from datetime import date, datetime, timezone
import os
from pathlib import Path
import re
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from fastapi import HTTPException
from psycopg.errors import LockNotAvailable
from sqlalchemy.exc import OperationalError

with patch.dict(os.environ, {"POSTGRES_HOST": "unused.invalid", "POSTGRES_DB": "test",
                             "POSTGRES_USER": "test", "POSTGRES_PASSWORD": "test"}):
    from app import clinical_store as store
from app.history_documents import check_history, comparable_journal, parse_history
from app.models import Patient

ID = 7
RECORD = "6ec12d52-872c-4d82-a6b8-235cbd99936c"
ENTRY = {"id": RECORD, "disease": "Reflujo", "treatment": "", "medication": "Omeprazol"}
CONSULTATION = SimpleNamespace(id="0b0e4e0e-7c5f-4a49-9d3c-1b1c0d4f8e21", model="modelo",
                               question="Primera línea\n\nTercera línea", direct_answer="Sin RAG",
                               rag_answer="Con RAG\n", created_at=datetime(2026, 11, 12, 10, tzinfo=timezone.utc))


def patient(name="Ana QA") -> Patient:
    return Patient(id=ID, name=name, birth_date=date(1990, 1, 2), email="ana@example.com")


def render_journal() -> str:
    rows = SimpleNamespace(all=lambda: [CONSULTATION])
    return store.render_journal(SimpleNamespace(scalars=lambda query: rows), ID)


# Se calcula antes de que las pruebas de recuperación sustituyan store.render_journal.
JOURNAL = render_journal()


class MarkdownRules(unittest.TestCase):
    def test_journal_comparison_ignores_trailing_spaces_and_final_newlines_r8(self):
        canonical = store.render(patient(), [ENTRY], JOURNAL)
        self.assertIn("\n> \n", canonical, "El formato escrito conserva '> ' con espacio")
        head = store.header(patient())
        cleaned = re.sub(r"\n+$", "", re.sub(r"(?m)[ \t]+$", "", canonical))
        self.assertEqual(check_history(cleaned, head, JOURNAL)[0], [ENTRY])
        self.assertEqual(check_history(canonical.replace("\n", "\r\n") + "\n\n", head, JOURNAL)[0], [ENTRY])
        for broken in (canonical.replace("Sin RAG", "Editado"), canonical.replace("> Tercera", ">  Tercera")):
            with self.assertRaisesRegex(ValueError, "Las consultas automáticas son históricas"):
                check_history(broken, head, JOURNAL)
        with self.assertRaisesRegex(ValueError, "Conserva la sección Consultas registradas"):
            check_history(store.render(patient(), [ENTRY], ""), head, JOURNAL)
        self.assertEqual(comparable_journal("a \n> \t\r\nb\n\n"), "a\n>\nb")

    def test_blank_lines_are_allowed_after_patient_id_r9(self):
        head = store.header(patient())
        body = store.render(patient(), [ENTRY], "")[len(head):]
        for blank in ("", "\n", "\n\n\n", "  \n\t\n"):
            with self.subTest(blank=blank):
                self.assertEqual(check_history(head + blank + body, head, "")[0], [ENTRY])
                self.assertEqual(check_history(head + blank, head, "")[0], [])
        with self.assertRaisesRegex(ValueError, "Estructura Markdown inválida"):
            check_history(head + "\nnota\n" + body, head, "")

    def test_same_structure_and_field_rules_as_java_r5(self):
        head = store.header(patient())
        canonical = store.render(patient(), [ENTRY], "")
        cases = {
            canonical.replace("Reflujo", "Reflujo\u2028# nota"): "Enfermedad: no admite caracteres de control",
            canonical.replace("Omeprazol", "\u00a0"): None,
            canonical.replace("\n\n### Enfermedad", "\n### Enfermedad"): "Usa Registro, Enfermedad",
            canonical.replace("\n\n### Tratamiento", "\n### Tratamiento"): "Usa Registro, Enfermedad",
            canonical.replace(RECORD, RECORD.upper()): "UUID válido y único",
            canonical.replace("Reflujo", "x\n# Título"): "Enfermedad: ninguna línea puede empezar",
            canonical.replace("Reflujo", "\u00a0").replace("Omeprazol", "No registrado."): "al menos un campo",
        }
        for markdown, message in cases.items():
            with self.subTest(message=message):
                if message is None:
                    # U+00A0 solo es un campo vacío para ambas APIs.
                    self.assertEqual(check_history(markdown, head, "")[0][0]["medication"], "")
                else:
                    with self.assertRaisesRegex(ValueError, message):
                        check_history(markdown, head, "")
        self.assertEqual(check_history(canonical.replace("Reflujo", "Texto #hashtag"), head, "")[0][0]["disease"],
                         "Texto #hashtag")

    def test_console_parser_reads_header_and_accepts_editor_cleaned_journal(self):
        markdown = re.sub(r"(?m)[ \t]+$", "", store.render(patient(), [ENTRY], JOURNAL))
        history = parse_history(markdown, "paciente-7-ana-qa.md")
        self.assertEqual((history["patient_id"], history["entries"]), (ID, [ENTRY]))
        self.assertEqual(history["consultations"][0]["question"], "Primera línea\n\nTercera línea")


class FakeDb:
    def __init__(self):
        self.rows = []
        self.deleted = []

    def add(self, row):
        self.rows.append(row)

    def delete(self, row):
        self.deleted.append(row)

    def flush(self):
        pass


class Recovery(unittest.TestCase):
    def setUp(self):
        self.directory = Path(self.enterContext(TemporaryDirectory()))
        self.enterContext(patch.object(store, "DIRECTORY", self.directory))
        self.enterContext(patch.dict(os.environ, {"HISTORY_SHARED_MARKER": ""}))
        self.db = FakeDb()
        self.journal = ""
        self.synchronizations = []
        self.enterContext(patch.object(store, "render_journal", lambda db, patient_id: self.journal))
        self.enterContext(patch.object(store, "latest_backup", self.latest))
        self.enterContext(patch.object(store, "sync_entries", lambda db, pid, entries: self.synchronizations.append(entries)))
        self.log = self.enterContext(patch.object(store, "log_event"))
        self.patient = patient()

    def latest(self, db, patient_id, *, recoverable=False):
        return next((row for row in reversed(self.db.rows) if not recoverable or row.kind != "deleted"), None)

    def valid(self):
        return store.render(self.patient, [ENTRY], "")

    def report(self):
        return self.directory / "paciente-7-ana-qa.md"

    def backup(self, markdown, kind="snapshot", digest=None):
        self.db.rows.append(SimpleNamespace(kind=kind, filename=self.report().name, markdown_content=markdown,
                                            revision=digest or store.revision(markdown)))

    def rejected(self):
        return sorted(self.directory.glob("paciente-7-ana-qa.md.rechazado-*"))

    def load(self):
        changes = store.FileChanges()
        return store.load(self.db, self.patient, changes), changes

    def test_invalid_utf8_is_set_aside_and_latest_valid_backup_restored_r10(self):
        self.backup(self.valid())
        damaged = self.valid().encode("utf-8") + b"\xff"
        self.report().write_bytes(damaged)

        (path, entries, _), _ = self.load()

        self.assertEqual((path, entries), (self.report(), [ENTRY]))
        self.assertEqual(self.report().read_text(encoding="utf-8"), self.valid())
        rejected, = self.rejected()
        self.assertEqual(rejected.read_bytes(), damaged)
        self.assertRegex(rejected.name, r"^paciente-7-ana-qa\.md\.rechazado-\d{8}T\d{6}Z(-\d+)?$")
        self.assertEqual(len(self.db.rows), 1, "El respaldo restaurado ya es el último: no se duplica")
        event = self.log.call_args
        self.assertEqual(event.args, ("history_recovered",))
        self.assertEqual((event.kwargs["patient_id"], event.kwargs["rejected"]), (ID, rejected.name))

    def test_foreign_header_journal_or_huge_file_also_recover(self):
        self.backup(self.valid())
        for content in (self.valid().replace("patient_id: 7", "patient_id: 8").encode(),
                        (self.valid() + "\n## Consultas registradas\n\nTexto que SQL no tiene.\n").encode(),
                        b"a" * (store.MAX_BYTES + 1)):
            self.report().write_bytes(content)
            self.load()
            self.assertEqual(self.report().read_text(encoding="utf-8"), self.valid())
        self.assertEqual(len(self.rejected()), 3, "Tres recuperaciones seguidas conservan los tres apartados")

    def test_without_valid_backup_the_file_is_kept_and_409_returned(self):
        self.backup(self.valid(), digest="0" * 64)
        self.backup(self.valid(), kind="deleted")
        broken = self.valid().replace("### Tratamiento", "### Otra")
        self.report().write_text(broken, encoding="utf-8")

        with self.assertRaises(HTTPException) as raised:
            self.load()

        self.assertEqual(raised.exception.status_code, 409)
        self.assertIn("no hay un respaldo válido", raised.exception.detail)
        self.assertEqual(self.report().read_text(encoding="utf-8"), broken)
        self.assertEqual(self.rejected(), [])

    def test_backup_with_other_journal_is_not_usable(self):
        self.journal = JOURNAL
        self.backup(self.valid())
        self.report().write_bytes(b"\xff")
        with self.assertRaises(HTTPException) as raised:
            self.load()
        self.assertEqual(raised.exception.status_code, 409)

    def test_rollback_restores_original_bytes_after_a_recovery(self):
        self.backup(self.valid())
        damaged = self.valid().replace("patient_id: 7", "patient_id: 9").encode()
        self.report().write_bytes(damaged)
        _, changes = self.load()
        changes.restore()
        self.assertEqual(self.report().read_bytes(), damaged)
        self.assertEqual(self.rejected(), [])

    def test_editor_cleaned_journal_is_accepted_without_rewriting(self):
        self.journal = JOURNAL
        markdown = re.sub(r"\n+$", "", re.sub(r"(?m)[ \t]+$", "", store.render(self.patient, [ENTRY], self.journal)))
        self.report().write_text(markdown, encoding="utf-8")
        self.load()
        self.assertEqual(self.report().read_text(encoding="utf-8"), markdown)
        self.assertEqual(self.rejected(), [])

    def test_stored_name_with_controls_is_409_but_can_be_renamed(self):
        legacy = patient("Ana\x07QA")
        self.patient = legacy
        self.report().write_text(store.render(legacy, [ENTRY], ""), encoding="utf-8")
        with self.assertRaises(HTTPException) as raised:
            self.load()
        self.assertEqual(raised.exception.status_code, 409)
        _, entries, _ = store.load(self.db, legacy, store.FileChanges(), check_name=False)
        self.assertEqual(entries, [ENTRY])

    def test_delete_works_with_unreadable_or_huge_file_j13(self):
        content = b"\xff\x00" + b"a" * (store.MAX_BYTES + 10)
        self.report().write_bytes(content)
        self.delete()
        deleted = self.db.rows[-1]
        self.assertEqual(deleted.kind, "deleted")
        self.assertTrue(deleted.markdown_content.startswith("\ufffd\ufffdaaa"))
        self.assertEqual(deleted.revision, store.revision(deleted.markdown_content))
        self.assertFalse(self.report().exists())
        self.assertEqual(self.db.deleted, [self.patient])

    def test_delete_without_file_leaves_deleted_backup(self):
        self.backup(self.valid())
        self.delete()
        self.assertEqual((self.db.rows[-1].kind, self.db.rows[-1].markdown_content), ("deleted", self.valid()))

    def delete(self):
        @contextmanager
        def transaction(db):
            yield store.FileChanges()

        with patch.object(store, "clinical_transaction", transaction), \
                patch.object(store, "patient_or_404", lambda db, patient_id: self.patient):
            store.delete_patient(self.db, ID)


class LockTimeoutR11(unittest.TestCase):
    def test_busy_lock_is_503_and_never_unlocked(self):
        statements = []

        class Session:
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
                statements.append(str(statement))
                if "pg_advisory_lock" in str(statement):
                    raise OperationalError("SELECT pg_advisory_lock", {}, LockNotAvailable("lock timeout"))

        with self.assertRaises(HTTPException) as raised:
            with store.clinical_transaction(Session()):
                self.fail("No debe entrar sin el bloqueo")
        self.assertEqual((raised.exception.status_code, raised.exception.detail),
                         (503, "La historia está ocupada por otra operación; reintenta."))
        self.assertEqual(statements[0], "SET LOCAL lock_timeout = '5s'")
        self.assertFalse(any("pg_advisory_unlock" in statement for statement in statements))


if __name__ == "__main__":
    unittest.main()
