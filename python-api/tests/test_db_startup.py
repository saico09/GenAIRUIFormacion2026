"""Pruebas aisladas: python -m unittest discover -s tests -v desde python-api."""

import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import MagicMock, patch

from psycopg.errors import ConnectionTimeout, InvalidPassword
from sqlalchemy.exc import OperationalError
from fastapi import HTTPException

# Solo valores ficticios; importar db crea el engine, sin abrir conexiones.
with patch.dict(os.environ, {
    "POSTGRES_HOST": "unused.invalid", "POSTGRES_DB": "test",
    "POSTGRES_USER": "test", "POSTGRES_PASSWORD": "never-log-test-password",
}):
    from app import db, clinical_store
    from app.clinical_store import require_shared_history


def unavailable():
    return OperationalError(None, None, ConnectionTimeout("never-log-test-password"))


class DatabaseStartupTests(unittest.TestCase):
    def setUp(self):
        self.now = 0.0
        self.engine = self.enterContext(patch.object(db, "engine"))
        self.execute_sql = MagicMock()
        self.engine.begin.return_value.__enter__.return_value.exec_driver_sql = self.execute_sql
        self.log = self.enterContext(patch.object(db, "log_event"))
        self.enterContext(patch.object(db, "monotonic", side_effect=lambda: self.now))
        self.sleep = self.enterContext(patch.object(db, "sleep", side_effect=self.advance))

    def advance(self, seconds):
        self.now += seconds

    def test_recovers_after_two_failed_connections(self):
        transaction = MagicMock()
        transaction.__enter__.return_value.exec_driver_sql = self.execute_sql
        self.engine.begin.side_effect = [unavailable(), unavailable(), transaction]

        db.initialize_database()

        self.assertEqual(self.engine.begin.call_count, 3)
        self.assertEqual(self.now, 4)
        self.execute_sql.assert_called_once()
        self.assertEqual(self.execute_sql.call_args.kwargs, {"execution_options": {"no_parameters": True}})
        self.assertEqual([c.kwargs["status"] for c in self.log.call_args_list],
                         ["waiting", "waiting", "ready"])
        self.assertNotIn("never-log-test-password", repr(self.log.call_args_list))

    def test_transaction_is_closed_before_retrying_initialization(self):
        first, second = MagicMock(), MagicMock()
        first.__enter__.return_value.exec_driver_sql = self.execute_sql
        second.__enter__.return_value.exec_driver_sql = self.execute_sql
        self.engine.begin.side_effect = [first, second]
        self.execute_sql.side_effect = [unavailable(), None]

        db.initialize_database()

        self.assertIs(first.__exit__.call_args.args[0], OperationalError)
        second.__exit__.assert_called_once_with(None, None, None)
        self.assertEqual(self.execute_sql.call_count, 2)

    def test_deadline_stops_retries_without_another_attempt(self):
        self.engine.begin.side_effect = unavailable()

        with self.assertRaisesRegex(RuntimeError, "plazo de 3 s"):
            db.initialize_database(timeout_seconds=3)

        self.assertEqual(self.now, 3)
        self.assertEqual(self.engine.begin.call_count, 2)
        self.assertEqual(self.log.call_args.kwargs["reason"], "deadline")
        self.execute_sql.assert_not_called()

    def test_last_connection_can_finish_after_retry_deadline(self):
        def timed_out():
            self.advance(db.CONNECT_TIMEOUT_SECONDS)
            raise unavailable()

        self.engine.begin.side_effect = timed_out
        with self.assertRaisesRegex(RuntimeError, "plazo de 10 s"):
            db.initialize_database(timeout_seconds=10)

        self.assertEqual(self.engine.begin.call_count, 2)
        self.assertEqual(self.now, 12)
        self.assertLessEqual(self.now, 10 + db.CONNECT_TIMEOUT_SECONDS)

    def test_permanent_sqlstate_fails_immediately_without_secrets(self):
        self.engine.begin.side_effect = OperationalError(
            None, None, InvalidPassword("never-log-test-password"))

        with self.assertRaisesRegex(RuntimeError, "SQLSTATE 28P01") as raised:
            db.initialize_database()

        self.engine.begin.assert_called_once()
        self.sleep.assert_not_called()
        self.assertEqual(self.log.call_args.kwargs["reason"], "permanent")
        self.assertNotIn("never-log-test-password", str(raised.exception))
        self.assertNotIn("never-log-test-password", repr(self.log.call_args_list))

    def test_non_operational_error_is_not_retried(self):
        self.execute_sql.side_effect = TypeError("esquema inválido")

        with self.assertRaisesRegex(TypeError, "esquema inválido"):
            db.initialize_database()

        self.engine.begin.assert_called_once()
        self.sleep.assert_not_called()

    def test_non_positive_deadline_is_rejected(self):
        with self.assertRaises(ValueError):
            db.initialize_database(timeout_seconds=0)
        self.engine.begin.assert_not_called()


class EngineConfigurationTests(unittest.TestCase):
    def test_real_sqlalchemy_engine_passes_five_second_timeout_to_psycopg(self):
        with patch.object(db.engine.dialect.dbapi, "connect", side_effect=ConnectionTimeout()) as connect:
            with self.assertRaises(OperationalError):
                db.engine.connect()
        self.assertEqual(connect.call_args.kwargs["connect_timeout"], 5)


class SharedHistoryMarkerTests(unittest.TestCase):
    """El guard sólo lee un marcador temporal; nunca monta datos ni abre PostgreSQL."""

    def setUp(self):
        self.directory = Path(self.enterContext(TemporaryDirectory()))
        self.marker = self.directory / ".genai-historias"
        self.enterContext(patch.dict(os.environ, {"HISTORY_SHARED_MARKER": str(self.marker)}))
        self.enterContext(patch.object(db.engine, "connect", side_effect=AssertionError("No debe abrir SQL")))

    def test_missing_marker_returns_503_without_creating_files(self):
        with self.assertRaises(HTTPException) as raised:
            require_shared_history()
        self.assertEqual(raised.exception.status_code, 503)
        self.assertEqual(list(self.directory.iterdir()), [])
        previous = self.directory / "informe-previo.md"
        previous.write_bytes(b"contenido previo")
        unmounted = self.directory / "montaje-ausente"
        with patch.object(clinical_store, "DIRECTORY", unmounted):
            with self.assertRaises(HTTPException):
                clinical_store.find_file(1)
            with self.assertRaises(HTTPException):
                clinical_store.atomic_write(previous, b"no guardar")
        self.assertFalse(unmounted.exists())
        self.assertEqual(previous.read_bytes(), b"contenido previo")

    def test_invalid_marker_returns_503_without_changing_content(self):
        for content in (b"otra-carpeta\n", b"\xff\xfe"):
            with self.subTest(content=content):
                self.marker.write_bytes(content)
                with self.assertRaises(HTTPException) as raised:
                    require_shared_history()
                self.assertEqual(raised.exception.status_code, 503)
                self.assertEqual(self.marker.read_bytes(), content)

    def test_valid_marker_allows_access_without_writing(self):
        content = b"genai-historias-v1\r\n"
        self.marker.write_bytes(content)
        require_shared_history()
        self.assertEqual(self.marker.read_bytes(), content)
        self.assertEqual(list(self.directory.iterdir()), [self.marker])

    def test_disabled_marker_never_reads_a_file(self):
        os.environ.pop("HISTORY_SHARED_MARKER", None)
        with patch.object(Path, "read_text", side_effect=AssertionError("Guard deshabilitado")):
            require_shared_history()
        self.assertEqual(list(self.directory.iterdir()), [])


if __name__ == "__main__":
    unittest.main()
