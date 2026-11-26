"""Contrato aislado del transporte LLM; no necesita Ollama, FastAPI ni PostgreSQL."""

import importlib.util
import json
from pathlib import Path
from types import ModuleType
import unittest
from unittest.mock import Mock, patch


# Importa el código real con sus dos dependencias sustituidas sólo durante la carga.
# Así la prueba no abre conexiones ni depende del entorno de la base de datos.
knowledge = ModuleType("app.knowledge")
knowledge.OLLAMA_BASE_URL = "http://unused.invalid:11434"
knowledge.OLLAMA_KEEP_ALIVE = "10m"
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
            "stream": False, "think": llm.THINK, "options": llm.MODEL_OPTIONS, "keep_alive": "10m",
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

    def test_native_durations_use_milliseconds_and_keep_cache_count(self):
        self.response.update(total_duration=91_234_567_890, load_duration=12_000_000_000,
                             prompt_eval_duration=34_500_000_000, eval_duration=44_734_567_890,
                             prompt_eval_cached_count=640)

        llm.llamar_llm("Relato")

        event = self.log.call_args.kwargs
        self.assertEqual(event["ollama_total_duration_ms"], 91234.568)
        self.assertEqual(event["ollama_load_duration_ms"], 12000.0)
        self.assertEqual(event["ollama_prompt_eval_duration_ms"], 34500.0)
        self.assertEqual(event["ollama_eval_duration_ms"], 44734.568)
        self.assertEqual(event["prompt_eval_cached_count"], 640)
        self.assertIn("duration_ms", event)  # Tiempo HTTP total medido por nuestra aplicación.

    def test_missing_or_invalid_native_metrics_remain_unknown(self):
        for value in (None, True, -1, "1000", 3.14):
            with self.subTest(value=value):
                self.response.update({name: value for name in (
                    "total_duration", "load_duration", "prompt_eval_duration", "eval_duration", "prompt_eval_cached_count")})
                llm.llamar_llm("Relato")
                event = self.log.call_args.kwargs
                for name in ("ollama_total_duration_ms", "ollama_load_duration_ms",
                             "ollama_prompt_eval_duration_ms", "ollama_eval_duration_ms", "prompt_eval_cached_count"):
                    self.assertIsNone(event[name])

    def test_incomplete_response_keeps_timings_without_exposing_partial_text(self):
        self.response.update(response="PARTIAL_SENTINEL_742", done_reason="length",
                             load_duration=0, eval_duration=123_000_000)
        with self.assertRaises(llm.LLMUnavailable):
            llm.llamar_llm("Relato")
        event = self.log.call_args.kwargs
        self.assertEqual(event["ollama_load_duration_ms"], 0.0)
        self.assertEqual(event["ollama_eval_duration_ms"], 123.0)
        self.assertNotIn("PARTIAL_SENTINEL_742", repr(self.log.call_args_list))

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

    def test_invalid_output_can_be_retried_but_transport_failure_cannot(self):
        self.request.return_value = {**self.response, "done_reason": "length"}
        with self.assertRaises(llm.LLMInvalidOutput):
            llm.llamar_llm("Relato")
        self.request.side_effect = OSError("sin conexión")
        with self.assertRaises(llm.LLMUnavailable) as raised:
            llm.llamar_llm("Relato")
        self.assertNotIsInstance(raised.exception, llm.LLMInvalidOutput)


class RetryTests(unittest.TestCase):
    def setUp(self):
        self.log = self.enterContext(patch.object(llm, "log_event"))

    def test_invalid_output_gets_exactly_one_more_attempt(self):
        generate = Mock(side_effect=["no es JSON", '{"ok": true}'])
        self.assertEqual(llm.con_un_reintento(generate, json.loads, branch="direct"), {"ok": True})
        self.assertEqual(generate.call_count, 2)
        self.assertEqual(self.log.call_args.args[0], "llm_retry")
        self.assertEqual(self.log.call_args.kwargs["branch"], "direct")

    def test_second_failure_is_raised_and_transport_failure_is_not_retried(self):
        generate = Mock(return_value="inválido")
        with self.assertRaises(ValueError):
            llm.con_un_reintento(generate, Mock(side_effect=ValueError("formato")), branch="rag")
        self.assertEqual(generate.call_count, 2)
        down = Mock(side_effect=llm.LLMUnavailable("LLM no disponible"))
        with self.assertRaises(llm.LLMUnavailable):
            llm.con_un_reintento(down, Mock(), branch="rag")
        self.assertEqual(down.call_count, 1)
        incomplete = Mock(side_effect=[llm.LLMInvalidOutput("LLM no disponible"), "ok"])
        self.assertEqual(llm.con_un_reintento(incomplete, lambda raw: raw, branch="rag"), "ok")

    def test_optional_correction_gets_the_invalid_response_and_specific_error(self):
        generate = Mock(return_value="bad JSON")
        correct = Mock(return_value='{"ok": true}')
        self.assertEqual(llm.con_un_reintento(generate, json.loads, branch="rag", corregir=correct), {"ok": True})
        generate.assert_called_once_with()
        self.assertEqual(correct.call_args.args[0], "bad JSON")
        self.assertIsInstance(correct.call_args.args[1], ValueError)
        self.assertEqual(correct.call_count, 1)
        with self.assertRaises(ValueError):
            llm.con_un_reintento(generate, json.loads, branch="rag", corregir=Mock(return_value="still bad"))

    def test_correction_receives_no_raw_output_after_truncation_and_skips_transport_errors(self):
        correct = Mock(return_value="ok")
        incomplete = Mock(side_effect=llm.LLMInvalidOutput("truncated"))
        self.assertEqual(llm.con_un_reintento(incomplete, str, branch="rag", corregir=correct), "ok")
        self.assertIsNone(correct.call_args.args[0])
        correct.reset_mock()
        with self.assertRaises(llm.LLMUnavailable):
            llm.con_un_reintento(Mock(side_effect=llm.LLMUnavailable("offline")), str, branch="rag", corregir=correct)
        correct.assert_not_called()

    def test_correction_system_unwraps_validation_error_and_bounds_previous_output(self):
        inner = ValueError("La condición repite un dato negado")
        outer = ValueError("Respuesta RAG con formato inválido")
        outer.__cause__ = inner
        system = llm.sistema_de_correccion("REGLAS", "x" * 5000, outer)
        self.assertTrue(system.startswith("REGLAS\n"))
        self.assertIn(str(inner), system)
        self.assertNotIn(str(outer), system)
        feedback = json.loads(system.rsplit("\n", 1)[1])
        self.assertEqual(len(feedback["salida_anterior"]), 4000)


if __name__ == "__main__":
    unittest.main()
