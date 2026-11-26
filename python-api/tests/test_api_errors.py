"""Códigos HTTP con TestClient, sin red ni PostgreSQL."""

from datetime import date
from io import BytesIO
import json
import unittest
from unittest.mock import patch
from urllib.error import HTTPError

from fastapi.testclient import TestClient
from psycopg.errors import ConnectionTimeout
from sqlalchemy.exc import OperationalError

from app import clinical, main, observability
from app.knowledge import QdrantUnavailable
from app.models import Patient

RECORD = "6ec12d52-872c-4d82-a6b8-235cbd99936c"


def unavailable():
    return OperationalError("SELECT 1", {}, ConnectionTimeout("sin conexión"))


class FakeSession:
    def __init__(self, patients=(), error=None):
        self.patients = {patient.id: patient for patient in patients}
        self.error = error

    def get(self, model, identifier):
        if self.error:
            raise self.error
        return self.patients.get(identifier)

    def scalars(self, query):
        if self.error:
            raise self.error
        return SimpleResult(list(self.patients.values()))


class SimpleResult(list):
    def all(self):
        return self


def java_error(code: int, detail) -> HTTPError:
    return HTTPError("http://java-api:8080/x", code, "error", {}, BytesIO(json.dumps({"detail": detail}).encode()))


class ApiErrors(unittest.TestCase):
    def setUp(self):
        self.enterContext(patch.object(observability, "write_transaction"))
        self.session = FakeSession([Patient(id=1, name="Ana", birth_date=date(1990, 1, 2), email="a@ex.com")])
        main.app.dependency_overrides[main.get_db] = lambda: self.session
        self.addCleanup(main.app.dependency_overrides.clear)
        # Sin "with": no ejecuta el arranque (PostgreSQL, informes ni trazas).
        self.client = TestClient(main.app, raise_server_exceptions=False)

    def test_route_ids_follow_r1(self):
        for path in ("/patients/0", "/patients/-1", "/patients/abc", "/patients/0x1", "/patients/1e3",
                     "/patients/99999999999", "/patients/2147483648", "/clinical/patients/99999999999/sync"):
            with self.subTest(path=path):
                method = self.client.post if path.startswith("/clinical") else self.client.get
                response = method(path)
                self.assertEqual(response.status_code, 422)
                self.assertEqual(response.json()["detail"], "patient_id debe ser un número entero entre 1 y 2147483647")
        self.assertEqual(self.client.get("/patients/2147483647").status_code, 404)
        self.assertEqual(self.client.get("/patients/01").json()["name"], "Ana")
        response = self.client.get(f"/patients/1/diseases/{RECORD[:-1]}")
        self.assertEqual((response.status_code, response.json()["detail"]), (422, "disease_id debe ser un UUID"))

    def test_record_uuid_is_normalized_before_lookup(self):
        with patch.object(main.clinical_store, "diseases", return_value=None) as diseases:
            response = self.client.get(f"/patients/1/diseases/{RECORD.upper()}")
        self.assertEqual(response.status_code, 404)
        self.assertEqual(diseases.call_args.args[1:], (1, RECORD))

    def test_invalid_input_is_422_without_echoing_values_r12_r13(self):
        body = '{"name":"Ana\\ud800","birth_date":"1990-01-02","email":"a@ex.com"}'
        response = self.client.post("/patients", content=body, headers={"Content-Type": "application/json"})
        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["detail"][0]["loc"], ["body", "name"])
        self.assertNotIn("input", response.json()["detail"][0])
        response = self.client.post("/chat", json={"patient_id": 1, "question": "dolor\u0000"})
        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["detail"][0]["msg"], "La consulta no admite caracteres de control")
        response = self.client.post("/patients/1/diseases", json={"disease": "x", "treatment": "", "medication": "\u2028"})
        self.assertEqual((response.status_code, response.json()["detail"][0]["loc"]), (422, ["body", "medication"]))

    def test_body_over_one_mib_is_413_r14(self):
        response = self.client.post("/patients", content=b"{" + b" " * 1048576 + b"}",
                                    headers={"Content-Type": "application/json"})
        self.assertEqual(response.status_code, 413)
        self.assertEqual(response.json()["detail"], "El cuerpo de la petición supera los límites permitidos")

    def test_database_down_is_503_not_500_j10(self):
        self.session.error = unavailable()
        for path in ("/patients", "/patients/1"):
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertEqual(response.status_code, 503)
                self.assertEqual(response.json()["detail"], main.DATABASE_UNAVAILABLE)

    def test_health_checks_postgres_e58(self):
        with patch.object(main.engine, "connect", side_effect=unavailable()):
            response = self.client.get("/health")
        self.assertEqual((response.status_code, response.json()["detail"]), (503, main.DATABASE_UNAVAILABLE))
        with patch.object(main.engine, "connect") as connect:
            response = self.client.get("/health")
        self.assertEqual((response.status_code, response.json()), (200, {"status": "ok"}))
        self.assertEqual(str(connect.return_value.__enter__.return_value.execute.call_args.args[0]), "SELECT 1")

    def test_delete_removes_index_as_best_effort_e04(self):
        with patch.object(main.clinical_store, "delete_patient") as deleted, \
                patch.object(main, "remove_patient_index", side_effect=QdrantUnavailable("caído")) as removed:
            response = self.client.delete("/patients/1")
        self.assertEqual(response.status_code, 204)
        deleted.assert_called_once()
        removed.assert_called_once_with(1)
        with patch.object(main.clinical_store, "delete_patient", side_effect=main.HTTPException(404, "Paciente no encontrado")), \
                patch.object(main, "remove_patient_index") as removed:
            self.assertEqual(self.client.delete("/patients/1").status_code, 404)
        removed.assert_not_called()

    def test_java_4xx_is_propagated_instead_of_503_j08(self):
        detail = "El informe Markdown no es válido (x) y no hay un respaldo válido; corrígelo o restáuralo"
        with patch.object(clinical, "request_json", side_effect=java_error(409, detail)):
            response = self.client.post("/clinical/patients/1/sync")
        self.assertEqual(response.json(), {"detail": detail})
        self.assertEqual(response.status_code, 409)
        with patch.object(clinical, "request_json", side_effect=java_error(500, "Error interno")):
            self.assertEqual(self.client.post("/clinical/patients/1/sync").status_code, 503)


class JavaClient(unittest.TestCase):
    def test_save_4xx_is_not_a_retryable_503(self):
        with patch.object(clinical, "request_json", side_effect=java_error(422, "El Markdown admite como máximo 1 MiB UTF-8")):
            with self.assertRaises(clinical.JavaRejected) as raised:
                clinical.save_consultation(1, RECORD, "pregunta", {"direct_answer": "a", "rag_answer": "b", "sources": []}, "m")
        self.assertEqual((raised.exception.status, raised.exception.detail), (422, "El Markdown admite como máximo 1 MiB UTF-8"))
        # Sigue siendo ClinicalUnavailable para quien ya la captura (índice pendiente).
        self.assertIsInstance(raised.exception, clinical.ClinicalUnavailable)

    def test_reused_uuid_keeps_409(self):
        responses = [java_error(409, "El UUID ya pertenece a otra consulta; no se sobrescribió"), java_error(404, "Consulta no encontrada")]
        with patch.object(clinical, "request_json", side_effect=responses):
            with self.assertRaises(clinical.JavaRejected) as raised:
                clinical.save_consultation(1, RECORD, "pregunta", {"direct_answer": "a", "rag_answer": "b", "sources": []}, "m")
        self.assertEqual(raised.exception.status, 409)

    def test_same_consultation_after_409_is_returned(self):
        saved = {"id": RECORD, "question": "pregunta"}
        with patch.object(clinical, "request_json", side_effect=[java_error(409, "x"), saved]):
            self.assertEqual(clinical.save_consultation(1, RECORD, "pregunta", {"direct_answer": "a", "rag_answer": "b",
                                                                                  "sources": []}, "m"), saved)

    def test_list_detail_is_kept(self):
        detail = [{"field": "direct_answer", "message": "size must be between 1 and 16000"}]
        with patch.object(clinical, "request_json", side_effect=java_error(422, detail)):
            with self.assertRaises(clinical.JavaRejected) as raised:
                clinical.get_clinical_patient(1)
        self.assertEqual(raised.exception.detail, detail)

    def test_cut_error_body_keeps_the_status(self):
        from http.client import IncompleteRead

        class CutBody(BytesIO):
            def read(self, *args):
                raise IncompleteRead(b"{", 10)
        error = HTTPError("http://java", 409, "Conflict", {}, CutBody())
        with patch.object(clinical, "request_json", side_effect=error):
            with self.assertRaises(clinical.JavaRejected) as raised:
                clinical.get_clinical_patient(1)
        self.assertEqual((raised.exception.status, raised.exception.detail), (409, "Java rechazó la operación"))


if __name__ == "__main__":
    unittest.main()
