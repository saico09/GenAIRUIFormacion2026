"""Contrato del flujo /chat sin red, LLM, base de datos ni pacientes reales."""

from types import SimpleNamespace
import json
import unittest
from unittest.mock import patch
from uuid import uuid4

from fastapi import HTTPException

from app import main


class ChatOrderTests(unittest.TestCase):
    def setUp(self):
        self.enterContext(patch("socket.socket.connect", side_effect=AssertionError("Red prohibida")))
        self.steps = []
        self.body = main.ChatIn(patient_id=71, question=" dolor de estómago agudo ")
        self.execution_id = str(uuid4())
        self.request = SimpleNamespace(state=SimpleNamespace(execution_id=self.execution_id, request_id="request-qa"))
        self.enterContext(patch.object(main, "get_clinical_patient", return_value={"id": 71, "name": "Paciente temporal"}))
        self.existing = self.enterContext(patch.object(main, "get_consultation", return_value=None))
        self.graph = self.enterContext(patch.object(main, "grafo"))
        self.direct = self.enterContext(patch.object(main, "llamar_llm"))
        self.save = self.enterContext(patch.object(main, "save_consultation"))
        self.sync = self.enterContext(patch.object(main, "sync_history"))
        self.tracer = self.enterContext(patch.object(main, "tracer"))
        self.sources = [{"source": "fixture.md", "section": "Enfermedad", "text": "Sólo para RAG"}]

        def run_graph(state):
            self.steps.append("rag")
            return {**state, "respuesta": "Orientación RAG", "fragmentos": self.sources}

        def run_direct(*args, **kwargs):
            self.steps.append("direct")
            return json.dumps({"mode": "symptom_guidance", "guidance": {
                "possibilities": [{"cause": "posibilidad de prueba", "condition": "un dato adicional"}],
                "optional_details": ["localización", "duración"], "current_alert": None}})

        def save(patient_id, execution_id, question, result, model):
            self.steps.append("save")
            return {**result, "id": execution_id, "created_at": "2026-11-11T12:00:00Z", "model": model}

        self.graph.invoke.side_effect = run_graph
        self.direct.side_effect = run_direct
        self.save.side_effect = save
        self.sync.side_effect = lambda patient_id: self.steps.append("index")

    def test_rag_then_direct_preserves_question_isolation_and_saves_only_complete_pair(self):
        result = main.chat(self.body, self.request)

        self.assertEqual(self.steps, ["rag", "direct", "save", "index"])
        self.graph.invoke.assert_called_once_with({"pregunta": self.body.question, "patient_id": 71,
                                                  "patient_name": "Paciente temporal", "request_id": "request-qa"})
        self.direct.assert_called_once_with(self.body.question, system=main.DIRECT_SYSTEM,
                                            schema=main.direct_response_schema(self.body.question))
        self.assertNotIn("Sólo para RAG", repr(self.direct.call_args))
        self.assertIn("Podría ser posibilidad de prueba si además hubiera un dato adicional", result["direct_answer"])
        self.assertIn("Para afinar la orientación, puedes añadir", result["direct_answer"])
        self.assertEqual(result["rag_answer"], "Orientación RAG")
        self.assertEqual(result["consultation"]["id"], self.execution_id)
        self.assertTrue(result["index_synced"])
        saved_args = self.save.call_args.args
        self.assertEqual(saved_args[:3], (71, self.execution_id, self.body.question))
        self.assertEqual(saved_args[-1], main.CHAT_MODEL)
        self.assertEqual(set(saved_args[3]), {"direct_answer", "rag_answer", "sources"})
        self.tracer.start_as_current_span.assert_called_once_with("rag", attributes={
            "openinference.span.kind": "CHAIN", "request_id": "request-qa"})

    def test_retry_uses_original_pair_without_generating_or_saving_again(self):
        self.existing.return_value = {"id": self.execution_id, "created_at": "2026-11-11T12:00:00Z",
                                      "direct_answer": "Original directa", "rag_answer": "Original RAG",
                                      "sources": [], "model": "modelo-original"}
        result = main.chat(self.body, self.request)
        self.assertEqual(result["model"], "modelo-original")
        self.assertEqual(self.steps, ["index"])
        self.graph.invoke.assert_not_called()
        self.direct.assert_not_called()
        self.save.assert_not_called()

    def test_rag_failure_does_not_run_direct_or_save_partial_consultation(self):
        self.graph.invoke.side_effect = main.LLMUnavailable("LLM no disponible")
        with self.assertRaises(HTTPException) as raised:
            main.chat(self.body, self.request)
        self.assertEqual(raised.exception.status_code, 503)
        self.direct.assert_not_called()
        self.save.assert_not_called()
        self.sync.assert_not_called()

    def test_direct_failure_after_rag_does_not_save_partial_consultation(self):
        self.direct.side_effect = main.LLMUnavailable("LLM no disponible")
        with self.assertRaises(HTTPException) as raised:
            main.chat(self.body, self.request)
        self.assertEqual(raised.exception.status_code, 503)
        self.assertEqual(self.steps, ["rag"])
        self.save.assert_not_called()
        self.sync.assert_not_called()

    def test_conflicting_execution_id_does_not_generate_or_overwrite(self):
        self.existing.side_effect = main.ConsultationConflict("UUID de otra consulta")
        with self.assertRaises(HTTPException) as raised:
            main.chat(self.body, self.request)
        self.assertEqual(raised.exception.status_code, 409)
        self.graph.invoke.assert_not_called()
        self.direct.assert_not_called()
        self.save.assert_not_called()
        self.sync.assert_not_called()

    def test_invalid_direct_orientation_does_not_persist_the_pair(self):
        self.direct.side_effect = None
        self.direct.return_value = json.dumps({"mode": "symptom_guidance", "guidance": "Narración libre"})
        with self.assertRaises(HTTPException) as raised:
            main.chat(self.body, self.request)
        self.assertEqual(raised.exception.status_code, 503)
        self.save.assert_not_called()
        self.sync.assert_not_called()


if __name__ == "__main__":
    unittest.main()
