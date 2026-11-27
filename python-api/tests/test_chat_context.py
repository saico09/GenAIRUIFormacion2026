"""Contexto RAG, colección en memoria y reintento del nodo LLM; sin red, Qdrant ni Ollama."""

import json
import unittest
import unittest.mock
from unittest.mock import patch

from app import history_index, knowledge
import grafo

RECORD = "263e4c3c-8db4-5b09-a711-bebc55a0828f"


def fragment(section, text, record=RECORD, score=0.5):
    return {"score": score, "patient_id": 1, "record_id": record, "source": "paciente-1-ana-demo.md",
            "section": section, "text": text}


def point(section, text, record=RECORD, score=0.5):
    data = fragment(section, text, record, score)
    return {"id": f"{record}-{section}", "score": data.pop("score"), "payload": {**data, "registry": "java"}}


class RecordContextTests(unittest.TestCase):
    def setUp(self):
        self.enterContext(patch("socket.socket.connect", side_effect=AssertionError("Red prohibida")))

    def test_each_retrieved_record_brings_its_three_sections_and_notes_go_last(self):
        retrieved = [fragment("Enfermedad", "ERGE"), fragment("Consulta", "dolor de estómago", record="c1"),
                     fragment("Medicamento", "omeprazol")]
        siblings = [point(section, text) for section, text in
                    (("Medicamento", "omeprazol"), ("Tratamiento", "cenar tres horas antes"), ("Enfermedad", "ERGE"))]
        with patch.object(knowledge, "qdrant", return_value={"result": {"points": siblings}}) as transport:
            context = knowledge.record_context(1, retrieved)
        self.assertEqual([(item["section"], item["text"]) for item in context],
                         [("Enfermedad", "ERGE"), ("Tratamiento", "cenar tres horas antes"),
                          ("Medicamento", "omeprazol"), ("Consulta", "dolor de estómago")])
        self.assertIs(context[0], retrieved[0])
        must = transport.call_args.args[2]["filter"]["must"]
        self.assertIn({"key": "record_id", "match": {"any": [RECORD]}}, must)
        self.assertIn({"key": "patient_id", "match": {"value": 1}}, must)

    def test_only_notes_or_complete_records_do_not_query_qdrant_and_other_patients_are_rejected(self):
        notes = [fragment("Consulta", "tos")]
        complete = [fragment("Medicamento", "omeprazol"), fragment("Enfermedad", "ERGE"), fragment("Tratamiento", "dieta")]
        with patch.object(knowledge, "qdrant") as transport:
            self.assertEqual(knowledge.record_context(1, notes), notes)
            self.assertEqual([item["section"] for item in knowledge.record_context(1, complete)],
                             ["Enfermedad", "Tratamiento", "Medicamento"])
        transport.assert_not_called()
        alien = point("Tratamiento", "otro paciente")
        alien["payload"]["patient_id"] = 2
        with patch.object(knowledge, "qdrant", return_value={"result": {"points": [alien]}}), \
             self.assertRaises(ValueError):
            knowledge.record_context(1, [fragment("Enfermedad", "ERGE")])

    def test_symptom_search_keeps_two_records_and_one_previous_note(self):
        confirmed = [point(section, section) for section in ("Enfermedad", "Tratamiento", "Medicamento")]
        notes = [point("Consulta", "dolor de estómago", record="c1")]

        def query(method, path, payload):
            section = payload["filter"]["must"][-1]["match"]
            return {"result": {"points": (notes if section.get("value") == "Consulta" else confirmed)[:payload["limit"]]}}
        with patch.object(knowledge, "HISTORY_AUTO_SYNC", False), patch.object(knowledge, "embed", return_value=[1.0]), \
             patch.object(knowledge, "qdrant", side_effect=query):
            result = knowledge.search_fragments(1, "dolor de estómago agudo")
        self.assertEqual([item["section"] for item in result], ["Enfermedad", "Tratamiento", "Consulta"])

    def test_three_retrieved_records_have_at_most_nine_context_sections(self):
        records = ("record-a", "record-b", "record-c")
        retrieved = [fragment("Enfermedad", f"Enfermedad {record}", record) for record in records]
        siblings = [point(section, f"{section} {record}", record) for record in records
                    for section in knowledge.CONFIRMED_SECTIONS]
        # Incluso una fila adicional ajena a los UUID solicitados no amplía el contexto.
        siblings.append(point("Medicamento", "Dato ajeno", "record-d"))
        with patch.object(knowledge, "qdrant", return_value={"result": {"points": siblings}}) as transport:
            context = knowledge.record_context(1, retrieved)
        self.assertEqual(len(retrieved), 3)
        self.assertEqual(len(context), 9)
        self.assertEqual({item["record_id"] for item in context}, set(records))
        self.assertEqual({item["patient_id"] for item in context}, {1})
        self.assertEqual({item["source"] for item in context}, {"paciente-1-ana-demo.md"})
        self.assertEqual(transport.call_args.args[2]["limit"], 9)


class CollectionCacheTests(unittest.TestCase):
    def setUp(self):
        self.enterContext(patch("socket.socket.connect", side_effect=AssertionError("Red prohibida")))
        knowledge.forget_collection()
        self.addCleanup(knowledge.forget_collection)

    def transport(self, method, url, data=None, **kwargs):
        if url.endswith("/collections"):
            return {"result": {"collections": [{"name": knowledge.COLLECTION}]}}
        return {"result": {"config": {"params": {"vectors": {"size": 3, "distance": "Cosine"}}}}}

    def test_collection_is_validated_once_and_forgotten_after_a_qdrant_failure(self):
        with patch.object(knowledge, "embed", return_value=[0.1, 0.2, 0.3]) as embed, \
             patch.object(knowledge, "request_json", side_effect=self.transport) as transport:
            first = knowledge.prepare_collection()
            self.assertEqual(knowledge.prepare_collection(), first)
            self.assertEqual((embed.call_count, transport.call_count), (1, 2))
            transport.side_effect = OSError("404: colección borrada")
            with self.assertRaises(knowledge.QdrantUnavailable):
                knowledge.qdrant("POST", f"/collections/{knowledge.COLLECTION}/points/scroll", {})
            transport.side_effect = self.transport
            self.assertEqual(knowledge.prepare_collection()["size"], 3)
            self.assertEqual(embed.call_count, 2)

    def test_unchanged_index_is_read_once_and_a_changed_index_is_verified_after_writing(self):
        expected = [{"id": "p1", "payload": {"patient_id": 1, "section": "Enfermedad", "text": "ERGE"}}]
        history = {"patient_id": 1, "filename": "paciente-1.md", "revision": "r", "entries": [{}]}
        with patch.object(history_index, "fragments_from_history", return_value=expected), \
             patch.object(history_index, "prepare_collection", return_value={"size": 2}):
            with patch.object(history_index, "patient_points", return_value=[{**expected[0], "vector": [0.1, 0.2]}]) as read, \
                 patch.object(history_index, "qdrant") as transport:
                self.assertEqual(history_index.index_history(history)["status"], "synced")
            self.assertEqual(read.call_count, 1)
            transport.assert_not_called()
            with patch.object(history_index, "patient_points", side_effect=[[], expected]) as read, \
                 patch.object(history_index, "embed", return_value=[0.3, 0.4]), \
                 patch.object(history_index, "qdrant") as transport:
                history_index.index_history(history)
            self.assertEqual(read.call_count, 2)
            self.assertEqual(transport.call_args.args[:2], ("PUT", f"/collections/{knowledge.COLLECTION}/points?wait=true"))

    def test_cut_response_body_counts_as_an_unavailable_service(self):
        from http.client import IncompleteRead
        response = unittest.mock.MagicMock()
        response.__enter__.return_value.read.side_effect = IncompleteRead(b"{", 10)
        with patch.object(knowledge, "urlopen", return_value=response):
            with self.assertRaises(OSError):
                knowledge.request_json("GET", "http://qdrant.invalid/collections")
            with self.assertRaises(knowledge.EmbeddingUnavailable):
                knowledge.embed("texto")

    def test_embeddings_use_the_configured_keep_alive(self):
        with patch.object(knowledge, "request_json", return_value={"embeddings": [[0.1, 0.2]]}) as transport:
            knowledge.embed("texto")
        self.assertEqual(transport.call_args.args[2]["keep_alive"], knowledge.OLLAMA_KEEP_ALIVE)


class PromptNodeTests(unittest.TestCase):
    def setUp(self):
        self.enterContext(patch("socket.socket.connect", side_effect=AssertionError("Red prohibida")))

    def test_prompt_node_receives_the_fragments_and_adds_the_complete_record(self):
        retrieved = [fragment("Enfermedad", "Ana Demo tiene ERGE."), fragment("Consulta", "dolor de estómago", record="c1")]
        siblings = [point("Tratamiento", "Cenar tres horas antes."), point("Medicamento", "Omeprazol.")]
        state = {"pregunta": "dolor de estómago agudo", "patient_id": 1, "request_id": "request-qa",
                 "patient_name": "Ana Demo", "fragmentos": retrieved}
        with patch.object(grafo, "record_context", wraps=knowledge.record_context), \
             patch.object(knowledge, "qdrant", return_value={"result": {"points": siblings}}):
            result = grafo.prompt(state)
        self.assertEqual(state["fragmentos"], retrieved)
        self.assertEqual([item["section"] for item in result["contexto"]],
                         ["Enfermedad", "Tratamiento", "Medicamento", "Consulta"])
        for item in result["contexto"]:
            self.assertIn(item["text"], result["prompt"])
        self.assertIn("(relato previo; no describe la consulta actual)\ndolor de estómago", result["prompt"])


class RagNodeRetryTests(unittest.TestCase):
    def setUp(self):
        self.enterContext(patch("socket.socket.connect", side_effect=AssertionError("Red prohibida")))
        self.state = {"pregunta": "dolor de estómago", "patient_id": 1, "request_id": "request-qa",
                      "contexto": [fragment("Enfermedad", "ERGE")], "prompt": "PROMPT"}
        self.valid = json.dumps({"mode": "symptom_guidance", "missing_information": False, "facts": [], "questions": [],
                                 "guidance": {"possibilities": [{"cause": "gastritis", "evidence": ["dolor de estómago"], "condition": None, "difference": None},
                                                               {"cause": "dispepsia", "evidence": ["dolor de estómago"], "condition": None, "difference": "Dato adicional que distingue esta alternativa de la principal"}],
                                              "optional_details": ["desde cuándo", "qué comió"], "current_alert": None}})

    def test_invalid_rag_output_gets_one_more_attempt_with_the_same_prompt(self):
        with patch.object(grafo, "llamar_llm", side_effect=["{no es JSON", self.valid]) as llm:
            self.assertEqual(grafo.llamada_llm(self.state), {"respuesta": self.valid})
        self.assertEqual(llm.call_count, 2)
        initial, retry = llm.call_args_list
        self.assertEqual(initial.args, retry.args)
        self.assertEqual(initial.kwargs["schema"], retry.kwargs["schema"])
        self.assertEqual(initial.kwargs["branch"], retry.kwargs["branch"])
        self.assertTrue(retry.kwargs["system"].startswith(initial.kwargs["system"]))
        self.assertIn("Expecting property name", retry.kwargs["system"])
        answer = grafo.respuesta({**self.state, "respuesta": self.valid})["respuesta"]
        self.assertIn("gastritis", answer)
        self.assertNotIn("si además hubiera dolor de estómago", answer)
        self.assertIn("ERGE\nFuente: [paciente-1-ana-demo.md/" + RECORD + "/Enfermedad]", answer)

    def test_two_invalid_outputs_fail_without_a_third_attempt(self):
        with patch.object(grafo, "llamar_llm", return_value="{no es JSON") as llm, self.assertRaises(ValueError):
            grafo.llamada_llm(self.state)
        self.assertEqual(llm.call_count, 2)

    def test_previous_symptom_lookup_uses_documentary_system_including_its_retry(self):
        from rag import DOCUMENTARY_SYSTEM, source_label
        source = fragment("Consulta", "Relató acidez después del café.", record="consulta-anterior")
        state = {**self.state, "pregunta": "¿Qué síntomas relató Ana Demo en su consulta anterior?",
                 "contexto": [source]}
        valid = json.dumps({"mode": "record_lookup", "missing_information": False, "guidance": None,
                            "facts": [{"source": source_label(source), "quote": source["text"]}], "questions": []})
        with patch.object(grafo, "llamar_llm", side_effect=["{mal formado", valid]) as llm:
            self.assertEqual(grafo.llamada_llm(state), {"respuesta": valid})
        initial, retry = llm.call_args_list
        self.assertEqual(initial.kwargs["schema"]["properties"]["mode"]["enum"], ["record_lookup"])
        self.assertEqual(initial.kwargs["system"], DOCUMENTARY_SYSTEM)
        self.assertTrue(retry.kwargs["system"].startswith(DOCUMENTARY_SYSTEM))
        self.assertEqual(initial.kwargs["schema"], retry.kwargs["schema"])
        self.assertEqual(initial.args, retry.args)
        shown = grafo.respuesta({**state, "respuesta": valid})["respuesta"]
        self.assertIn(source["text"], shown)
        self.assertNotIn("Diagnóstico orientativo", shown)


if __name__ == "__main__":
    unittest.main()
