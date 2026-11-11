"""Contrato aislado del transporte LLM; no necesita Ollama, FastAPI ni PostgreSQL."""

import importlib.util
from pathlib import Path
from types import ModuleType
import unittest
from unittest.mock import Mock, patch


# Importa el código real con sus dos dependencias sustituidas sólo durante la carga.
# Así la prueba no abre conexiones ni depende del entorno de la base de datos.
knowledge = ModuleType("app.knowledge")
knowledge.OLLAMA_BASE_URL = "http://unused.invalid:11434"
knowledge.request_json = Mock()
observability = ModuleType("app.observability")
observability.log_event = Mock()
spec = importlib.util.spec_from_file_location(
    "llm_under_test", Path(__file__).resolve().parents[1] / "app" / "llm.py")
llm = importlib.util.module_from_spec(spec)
with patch.dict("sys.modules", {"app.knowledge": knowledge, "app.observability": observability}):
    spec.loader.exec_module(llm)


class LLMTransportTests(unittest.TestCase):
    def setUp(self):
        self.request = self.enterContext(patch.object(llm, "request_json"))
        self.log = self.enterContext(patch.object(llm, "log_event"))
        self.response = {
            "response": "  Respuesta final.\n", "done": True, "done_reason": "stop",
            "prompt_eval_count": 1500, "eval_count": 120,
        }
        self.request.return_value = self.response

    def test_success_keeps_transport_and_records_generation_metadata(self):
        answer = llm.llamar_llm("Relato", system="Instrucciones")

        self.assertEqual(answer, "Respuesta final.")
        method, url, body = self.request.call_args.args
        self.assertEqual((method, url), ("POST", "http://unused.invalid:11434/api/generate"))
        self.assertEqual(body, {
            "model": llm.CHAT_MODEL, "prompt": "Relato", "system": "Instrucciones",
            "stream": False, "think": llm.THINK, "options": llm.MODEL_OPTIONS, "keep_alive": "1m",
        })
        self.assertEqual(self.request.call_args.kwargs, {"timeout": llm.TIMEOUT_SECONDS})
        self.log.assert_called_once()
        event = self.log.call_args.kwargs
        self.assertEqual(event["status"], "ok")
        self.assertEqual(event["response"], answer)
        self.assertEqual((event["prompt_eval_count"], event["eval_count"], event["done_reason"]),
                         (1500, 120, "stop"))
        self.assertEqual(event["model_options"], llm.MODEL_OPTIONS)
        self.assertIsNot(event["model_options"], llm.MODEL_OPTIONS)
        self.assertIs(event["thinking_returned"], False)
        self.assertIs(event["think_requested"], False)

    def test_schema_branch_keeps_same_model_and_options(self):
        schema = {"type": "object", "properties": {"answer": {"type": "string"}}}
        self.response["response"] = '{"answer":"Texto"}'

        self.assertEqual(llm.llamar_llm("Relato", branch="rag", schema=schema, system="Sistema"),
                         '{"answer":"Texto"}')

        body = self.request.call_args.args[2]
        self.assertEqual(body["format"], schema)
        self.assertEqual(body["options"], llm.MODEL_OPTIONS)
        self.assertEqual(body["model"], llm.CHAT_MODEL)
        self.assertEqual(body["system"], "Sistema")
        self.assertEqual(self.log.call_args.kwargs["branch"], "rag")

    def test_thinking_is_never_returned_or_logged(self):
        self.response["thinking"] = "REASONING_SENTINEL_742"

        answer = llm.llamar_llm("Relato")

        self.assertEqual(answer, "Respuesta final.")
        self.assertIs(self.log.call_args.kwargs["thinking_returned"], True)
        self.assertNotIn("REASONING_SENTINEL_742", repr(self.log.call_args_list))
        self.assertNotIn("thinking", self.log.call_args.kwargs)

    def test_empty_incomplete_and_truncated_responses_are_rejected(self):
        cases = [
            {"response": ""}, {"response": " \n\t"}, {"response": None},
            {"response": 42}, {"done": False}, {"done_reason": "length"},
        ]
        for changes in cases:
            with self.subTest(changes=changes):
                self.request.return_value = {**self.response, **changes,
                                             "thinking": "REJECTED_REASONING_742"}
                self.log.reset_mock()
                with self.assertRaisesRegex(llm.LLMUnavailable, "^LLM no disponible$"):
                    llm.llamar_llm("Relato")
                self.log.assert_called_once()
                event = self.log.call_args.kwargs
                self.assertEqual(event["status"], "error")
                self.assertIsNone(event["response"])
                self.assertIs(event["thinking_returned"], True)
                self.assertEqual(event["done_reason"], changes.get("done_reason", "stop"))
                self.assertEqual((event["prompt_eval_count"], event["eval_count"]), (1500, 120))
                self.assertNotIn("REJECTED_REASONING_742", repr(self.log.call_args_list))

    def test_thinking_without_final_response_is_not_used_as_answer(self):
        self.request.return_value = {
            "thinking": "ONLY_REASONING_742", "done": True, "done_reason": "length",
            "prompt_eval_count": 600, "eval_count": 1024,
        }

        with self.assertRaises(llm.LLMUnavailable):
            llm.llamar_llm("Relato")

        event = self.log.call_args.kwargs
        self.assertIsNone(event["response"])
        self.assertEqual(event["done_reason"], "length")
        self.assertEqual(event["eval_count"], 1024)
        self.assertIs(event["thinking_returned"], True)
        self.assertNotIn("ONLY_REASONING_742", repr(self.log.call_args_list))

    def test_optional_or_invalid_token_counts_are_not_fabricated(self):
        self.request.return_value = {
            "response": "Texto", "done": True, "prompt_eval_count": True, "eval_count": -1,
        }

        self.assertEqual(llm.llamar_llm("Relato"), "Texto")

        event = self.log.call_args.kwargs
        self.assertIsNone(event["prompt_eval_count"])
        self.assertIsNone(event["eval_count"])
        self.assertIsNone(event["done_reason"])
        self.assertIs(event["thinking_returned"], False)

    def test_transport_failure_logs_no_exception_body_or_fabricated_tokens(self):
        self.request.side_effect = OSError("PRIVATE_TRANSPORT_DETAIL_742")

        with self.assertRaisesRegex(llm.LLMUnavailable, "^LLM no disponible$"):
            llm.llamar_llm("Relato")

        event = self.log.call_args.kwargs
        self.assertEqual(event["status"], "error")
        self.assertIsNone(event["response"])
        self.assertIsNone(event["prompt_eval_count"])
        self.assertIsNone(event["eval_count"])
        self.assertIsNone(event["done_reason"])
        self.assertNotIn("PRIVATE_TRANSPORT_DETAIL_742", repr(self.log.call_args_list))

    def test_malformed_or_missing_response_is_rejected(self):
        for result in (None, [], {"done": True}):
            with self.subTest(result=result):
                self.request.return_value = result
                self.log.reset_mock()
                with self.assertRaises(llm.LLMUnavailable):
                    llm.llamar_llm("Relato")
                self.log.assert_called_once()
                self.assertEqual(self.log.call_args.kwargs["status"], "error")


if __name__ == "__main__":
    unittest.main()
