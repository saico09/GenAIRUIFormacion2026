"""Contratos offline: ejecutar por stdin dentro de python-api; no conecta servicios ni usa el LLM."""

import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from uuid import UUID

from app import clinical_proposals, history_index, knowledge
from app.history_documents import fragments_from_history, load_histories, parse_history
from rag import is_record_lookup, rag_response_schema, source_label, validate_rag_answer


RECORD = "02b2f5e5-2cd0-4e90-b6a3-a40c864824fa"
OTHER = "ad544594-cd33-49d0-9afd-46d9a370cfa8"
FILENAME = "paciente-71-prueba-demo.md"


def document(*, record=RECORD, disease="Enfermedad Prueba", treatment="Tratamiento Prueba",
             medication="Medicamento Prueba"):
    return ("# Historia clínica ficticia — Prueba Demo\n\n"
            "Datos ficticios para la formación.\n\npatient_id: 71\n\n"
            f"## Registro {record}\n\n### Enfermedad\n{disease}\n\n"
            f"### Tratamiento\n{treatment}\n\n### Medicamento\n{medication}\n")


class OfflineContracts(unittest.TestCase):
    def setUp(self):
        # Un error del ensayo no debe convertirse en una llamada externa accidental.
        self.network = patch("socket.socket.connect", side_effect=AssertionError("Red prohibida en contrato offline"))
        self.network.start()
        self.addCleanup(self.network.stop)

    def test_crlf_revision_identifies_original_bytes_without_writing(self):
        raw = document().replace("\n", "\r\n").encode("utf-8")
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / FILENAME
            path.write_bytes(raw)
            loaded = load_histories(Path(directory))[0]
            self.assertEqual(loaded["revision"], hashlib.sha256(raw).hexdigest())
            self.assertEqual(loaded["markdown"].encode("utf-8"), raw)
            self.assertEqual(path.read_bytes(), raw)
            self.assertNotEqual(loaded["revision"], hashlib.sha256(raw.replace(b"\r\n", b"\n")).hexdigest())

    def test_header_and_uuid_must_be_canonical(self):
        originals = document()
        bad = [originals.replace("Datos ficticios para la formación.", "Otro preámbulo"),
               originals.replace("## Registro", "## Registo"),
               document(record=RECORD.upper()), document(record="not-a-uuid"),
               originals.replace("### Tratamiento", "### Medicamento"),
               document(disease="Dato\n###### Encabezado no permitido")]
        for markdown in bad:
            with self.subTest(markdown=markdown[:50]):
                with self.assertRaises(ValueError):
                    parse_history(markdown, FILENAME)
        with self.assertRaises(ValueError):
            parse_history(originals, "paciente-72-prueba-demo.md")
        duplicate = originals + "\n## Registro " + originals.split("\n## Registro ", 1)[1]
        with self.assertRaises(ValueError):
            parse_history(duplicate, FILENAME)

    def test_body_patient_id_is_text_not_owner_metadata(self):
        history = parse_history(document(disease="Observación literal\npatient_id: 72"), FILENAME)
        self.assertEqual(history["patient_id"], 71)
        self.assertIn("patient_id: 72", history["entries"][0]["disease"])

    def test_unknown_fields_and_limits(self):
        history = parse_history(document(treatment="No registrado.", medication="No registrado."), FILENAME)
        self.assertEqual(history["entries"][0]["treatment"], "")
        self.assertEqual(history["entries"][0]["medication"], "")
        for markdown in (document(disease="No registrado.", treatment="No registrado.", medication="No registrado."),
                         document(disease="x" * 2001), document(disease="ñ" * 40000)):
            with self.assertRaises(ValueError):
                parse_history(markdown, FILENAME)
        header = document().split("\n## Registro ", 1)[0]
        entries = [document(record=str(UUID(int=n))).split("\n## Registro ", 1)[1] for n in range(1, 52)]
        accepted = header + "".join("\n## Registro " + entry for entry in entries[:50])
        self.assertEqual(len(parse_history(accepted, FILENAME)["entries"]), 50)
        with self.assertRaises(ValueError):
            parse_history(accepted + "\n## Registro " + entries[50], FILENAME)

    def test_fragment_ids_survive_edit_and_keep_records_separate(self):
        first = fragments_from_history(parse_history(document(), FILENAME))
        edited = fragments_from_history(parse_history(document(disease="Dato editado"), FILENAME))
        self.assertEqual([point["id"] for point in first], [point["id"] for point in edited])
        self.assertNotEqual(first[0]["payload"]["revision"], edited[0]["payload"]["revision"])
        second = document(record=OTHER).split("\n## Registro ", 1)[1]
        six = fragments_from_history(parse_history(document() + "\n## Registro " + second, FILENAME))
        self.assertEqual(len({point["id"] for point in six}), 6)
        self.assertEqual({point["payload"]["record_id"] for point in six}, {RECORD, OTHER})
        self.assertTrue(all(point["payload"]["patient_id"] == 71 and point["payload"]["registry"] == "java" for point in six))

    def test_current_fragments_are_not_reembedded_or_rewritten(self):
        history = parse_history(document(), FILENAME)
        points = fragments_from_history(history)
        # La comprobación de colección tiene su propio embedding de prueba;
        # aquí verificamos sólo que los fragmentos ya vigentes no se reprocesen.
        with patch.object(history_index, "prepare_collection", return_value={"size": 3}), \
             patch.object(history_index, "patient_points", return_value=points), \
             patch.object(history_index, "embed") as embed, patch.object(history_index, "qdrant") as transport:
            result = history_index.index_history(history)
        self.assertEqual(result["fragments"], 3)
        embed.assert_not_called()
        transport.assert_not_called()

    def test_embedding_failure_does_not_upsert_or_delete_existing_index(self):
        history = parse_history(document(), FILENAME)
        with patch.object(history_index, "prepare_collection", return_value={"size": 3}), \
             patch.object(history_index, "patient_points", return_value=[]), \
             patch.object(history_index, "embed", side_effect=OSError("Fallo simulado")), \
             patch.object(history_index, "qdrant") as transport:
            with self.assertRaises(OSError):
                history_index.index_history(history)
        transport.assert_not_called()

    def test_new_consultation_reuses_previous_vectors_when_only_revision_changes(self):
        history = parse_history(document(), FILENAME)
        old = [{**p, "vector": [0.1, 0.2, 0.3]} for p in fragments_from_history(history)]
        history["revision"] = "b" * 64
        history["consultations"] = [{"id": OTHER, "created_at": "2026-11-07T20:00:00Z", "question": "dolor desde ayer"}]
        expected = fragments_from_history(history)
        with patch.object(history_index, "prepare_collection", return_value={"size": 3}), \
             patch.object(history_index, "patient_points", side_effect=[old, expected]), \
             patch.object(history_index, "embed", return_value=[0.4, 0.5, 0.6]) as embed, \
             patch.object(history_index, "qdrant") as transport:
            result = history_index.index_history(history)
        self.assertEqual(result["fragments"], 4)
        embed.assert_called_once()
        sent = transport.call_args.args[2]["points"]
        self.assertEqual([p["vector"] for p in sent[:3]], [[0.1, 0.2, 0.3]] * 3)
        self.assertEqual(sent[-1]["vector"], [0.4, 0.5, 0.6])
        self.assertTrue(all(p["payload"]["revision"] == history["revision"] for p in sent))

    def test_explicit_journal_lookup_can_retrieve_symptoms_among_previous_questions(self):
        confirmed = [{**p, "score": 0.8} for p in fragments_from_history(parse_history(document(), FILENAME))]
        notes = [{"id": str(UUID(int=n)), "score": 0.9-n/100, "payload": {
            "patient_id": 71, "record_id": str(UUID(int=n)), "source": FILENAME,
            "section": "Consulta", "text": text}} for n, text in enumerate([
                "Resume la enfermedad", "Qué cirugía tiene", "dolor estomacal y diarrea"], 1)]

        def query(method, path, payload):
            condition = payload["filter"]["must"][-1]
            data = notes if condition.get("match", {}).get("value") == "Consulta" else confirmed
            return {"result": {"points": data[:payload["limit"]]}}

        with patch.object(knowledge, "HISTORY_AUTO_SYNC", False), \
             patch.object(knowledge, "embed", return_value=[1.0]), patch.object(knowledge, "qdrant", side_effect=query):
            journal = knowledge.search_fragments(71, "¿Qué síntomas relató el paciente en consultas anteriores?")
            medical = knowledge.search_fragments(71, "¿Qué enfermedad tiene?")
        self.assertEqual(len(journal), 3)
        self.assertIn("dolor estomacal y diarrea", [item["text"] for item in journal])
        self.assertTrue(all(item["section"] == "Consulta" for item in journal))
        self.assertTrue(all(item["section"] != "Consulta" for item in medical))

    def test_evidence_rejects_question_negation_and_invented_quotes(self):
        value = "Enfermedad Prueba"
        self.assertTrue(clinical_proposals.affirmative_evidence("Diagnóstico registrado: Enfermedad Prueba.", value, value))
        for note, evidence in (("¿Tiene Enfermedad Prueba?", value),
                               ("Niega Enfermedad Prueba.", value),
                               ("No tiene Enfermedad Prueba.", value),
                               ("Solo hay dolor de cabeza.", value),
                               ("Diagnóstico registrado: Enfermedad Prueba.", "Texto inventado")):
            self.assertFalse(clinical_proposals.affirmative_evidence(note, evidence, value))

    def test_proposal_returns_draft_without_storage_or_index_calls(self):
        note = "Diagnóstico registrado: Enfermedad Prueba."
        model_entry = {field: "" for field in clinical_proposals.FIELDS}
        model_entry["disease"] = "Enfermedad Prueba"
        with patch.object(clinical_proposals, "get_clinical_patient", return_value={"id": 71, "name": "Prueba Demo"}), \
             patch.object(clinical_proposals, "llamar_llm", return_value=json.dumps({"entries": [model_entry]})) as llm, \
             patch("app.clinical.request_json") as java_transport, \
             patch.object(history_index, "qdrant") as index_transport, \
             patch("pathlib.Path.write_text") as write_text, patch("pathlib.Path.write_bytes") as write_bytes:
            response = clinical_proposals.propose_entries(71, note)
        self.assertEqual(response["entries"][0]["disease"], "Enfermedad Prueba")
        self.assertEqual(response["entries"][0]["evidence"]["disease"], note)
        self.assertNotIn("id", response["entries"][0])
        self.assertEqual(llm.call_args.kwargs["branch"], "clinical_proposal")
        self.assertEqual(llm.call_args.kwargs["schema"], clinical_proposals.PROPOSAL_SCHEMA)
        for action in (java_transport, index_transport, write_text, write_bytes):
            action.assert_not_called()

    def test_model_cannot_turn_question_quote_into_a_saved_fact(self):
        entry = {field: "" for field in clinical_proposals.FIELDS}
        entry["disease"] = "Enfermedad Prueba"
        with patch.object(clinical_proposals, "get_clinical_patient", return_value={"id": 71, "name": "Prueba Demo"}), \
             patch.object(clinical_proposals, "llamar_llm", return_value=json.dumps({"entries": [entry]})):
            response = clinical_proposals.propose_entries(71, "¿Tiene Enfermedad Prueba?")
        self.assertEqual(response["entries"], [])

    def test_proposal_requires_affirmative_cue_for_the_selected_field(self):
        for note, value in (("Se anotó Prueba.", "Prueba"),
                            ("Hay dolor de cabeza.", "dolor de cabeza"),
                            ("Tratamiento registrado: Prueba.", "Prueba")):
            entry = {"disease": value, "treatment": "", "medication": ""}
            with self.subTest(note=note), \
                 patch.object(clinical_proposals, "get_clinical_patient", return_value={"id": 71, "name": "Prueba Demo"}), \
                 patch.object(clinical_proposals, "llamar_llm", return_value=json.dumps({"entries": [entry]})):
                self.assertEqual(clinical_proposals.propose_entries(71, note)["entries"], [])

    def test_proposal_null_model_value_is_an_explicit_error(self):
        entry = {"disease": None, "treatment": "", "medication": ""}
        with patch.object(clinical_proposals, "get_clinical_patient", return_value={"id": 71, "name": "Prueba Demo"}), \
             patch.object(clinical_proposals, "llamar_llm", return_value=json.dumps({"entries": [entry]})):
            with self.assertRaises(clinical_proposals.LLMUnavailable):
                clinical_proposals.propose_entries(71, "Diagnóstico registrado: Enfermedad Prueba.")

    def test_rag_three_literal_facts_keep_their_uuid_and_source(self):
        sources = [point["payload"] for point in fragments_from_history(parse_history(document(), FILENAME))]
        facts = [{"source": source_label(source), "quote": source["text"]} for source in sources]
        raw = json.dumps({"facts": facts, "missing_information": False})
        rendered = validate_rag_answer(raw, sources)
        self.assertEqual(rendered.count("Respuesta:"), 3)
        for fact in facts:
            self.assertIn(f"Respuesta: {fact['quote']}\nFuente: {fact['source']}", rendered)
            self.assertIn(RECORD, fact["source"])
        schema = rag_response_schema(sources)
        self.assertEqual(schema["properties"]["facts"]["items"]["properties"]["source"]["enum"],
                         [source_label(source) for source in sources])
        self.assertEqual(rag_response_schema([])["properties"]["facts"]["maxItems"], 0)

    def test_rag_rejects_fabricated_quote_source_and_non_json(self):
        sources = [point["payload"] for point in fragments_from_history(parse_history(document(), FILENAME))]
        valid_source = source_label(sources[0])
        bad = ["Respuesta: Enfermedad Prueba\nFuente: " + valid_source,
               json.dumps({"facts": [{"source": valid_source, "quote": "Diagnóstico inventado"}], "missing_information": False}),
               json.dumps({"facts": [{"source": valid_source.replace(RECORD, OTHER), "quote": sources[0]["text"]}], "missing_information": False}),
               json.dumps({"facts": [{"source": valid_source, "quote": sources[1]["text"]}], "missing_information": False}),
               json.dumps({"facts": [], "missing_information": "false"})]
        for answer in bad:
            with self.subTest(answer=answer):
                self.assertEqual(validate_rag_answer(answer, sources), "No hay información suficiente")

    def test_rag_abstains_on_missing_or_any_unrecorded_fact(self):
        sources = [point["payload"] for point in fragments_from_history(
            parse_history(document(medication="No registrado."), FILENAME))]
        raw = json.dumps({"facts": [{"source": source_label(source), "quote": source["text"]}
                                    for source in (sources[0], sources[2])], "missing_information": False})
        rendered = validate_rag_answer(raw, sources)
        self.assertEqual(rendered, "No hay información suficiente")
        partial = json.dumps({"facts": [{"source": source_label(sources[0]), "quote": sources[0]["text"]}],
                              "missing_information": True})
        self.assertEqual(validate_rag_answer(partial, sources), "No hay información suficiente")
        self.assertEqual(validate_rag_answer(json.dumps({"facts": [], "missing_information": True}), sources),
                         "No hay información suficiente")

    def test_record_lookup_accepts_paraphrases_and_first_person_records(self):
        questions = ("¿Cuál es el diagnóstico registrado?", "Dime lo que consta en mi historia.",
                     "Resume la enfermedad, el tratamiento y el medicamento registrados.",
                     "¿Qué tratamiento tengo registrado?", "¿Qué enfermedad tengo documentada?",
                     "¿En qué fecha se registró la consulta?")
        sources = [point["payload"] for point in fragments_from_history(parse_history(document(), FILENAME))]
        raw = json.dumps({"facts": [{"source": source_label(sources[0]), "quote": sources[0]["text"]}],
                          "missing_information": False})
        for question in questions:
            with self.subTest(question=question):
                self.assertTrue(is_record_lookup(question))
                self.assertIn("Fuente: " + source_label(sources[0]), validate_rag_answer(raw, sources, question))

    def test_missing_documentary_information_does_not_turn_into_general_guidance(self):
        sources = [point["payload"] for point in fragments_from_history(parse_history(document(), FILENAME))]
        raw = json.dumps({"facts": [{"source": source_label(sources[0]), "quote": sources[0]["text"]}],
                          "mode": "record_lookup", "missing_information": True,
                          "guidance": "Un texto general no responde el dato ausente", "questions": []})
        questions = ("¿Cuál es la fecha de nacimiento del paciente?",
                     "¿Qué cirugía tiene programada?")
        for question in questions:
            with self.subTest(question=question):
                self.assertTrue(is_record_lookup(question))
                self.assertEqual(validate_rag_answer(raw, sources, question), "No hay información suficiente")

    def test_symptom_guidance_does_not_require_a_preexisting_diagnosis(self):
        raw = json.dumps({"mode": "symptom_guidance", "missing_information": True, "facts": [],
                          "guidance": "Una posibilidad es dispepsia si predomina la molestia tras comer; faltan datos para priorizar una causa.",
                          "questions": []})
        rendered = validate_rag_answer(raw, [], "dolor de estómago desde ayer")
        self.assertIn("Diagnóstico orientativo (sin confirmar)", rendered)
        self.assertIn("Una posibilidad es dispepsia", rendered)
        self.assertNotIn("?", rendered)
        self.assertNotIn("Fuente:", rendered)

    def test_guidance_schema_and_render_do_not_enable_a_questionnaire(self):
        self.assertEqual(rag_response_schema([])["properties"]["questions"]["maxItems"], 0)
        raw = json.dumps({"mode": "symptom_guidance", "missing_information": True, "facts": [],
                          "guidance": "Podría ser reflujo por su relación con comidas.",
                          "questions": ["¿Tiene síntomas?", "¿Cuándo comenzó?"]})
        rendered = validate_rag_answer(raw, [], "Acidez después de comer, sin otros síntomas.")
        self.assertNotIn("¿Tiene síntomas?", rendered)
        self.assertNotIn("¿Cuándo comenzó?", rendered)
        self.assertNotIn("Para aclarar la consulta", rendered)

    def test_existing_treatment_quote_is_not_evidence_of_surgery(self):
        sources = [point["payload"] for point in fragments_from_history(parse_history(document(), FILENAME))]
        raw = json.dumps({"mode": "record_lookup", "missing_information": False,
                          "facts": [{"source": source_label(sources[1]), "quote": sources[1]["text"]}],
                          "guidance": "", "questions": []})
        self.assertEqual(validate_rag_answer(raw, sources, "¿Cuál fue la última cirugía registrada?"),
                         "No hay información suficiente")
        self.assertIn("Tratamiento Prueba", validate_rag_answer(raw, sources, "¿Qué tratamiento sigue?"))

    def test_guidance_never_presents_a_fabricated_quote_as_background(self):
        sources = [point["payload"] for point in fragments_from_history(parse_history(document(), FILENAME))]
        raw = json.dumps({"mode": "symptom_guidance", "missing_information": True,
                          "facts": [{"source": source_label(sources[0]), "quote": "Diagnóstico inventado"}],
                          "guidance": "Conviene aclarar lo que describes [archivo-inventado.md].", "questions": []})
        rendered = validate_rag_answer(raw, sources, "dolor de cabeza")
        self.assertIn("Diagnóstico orientativo (sin confirmar)", rendered)
        self.assertNotIn("Diagnóstico inventado", rendered)
        self.assertNotIn("archivo-inventado", rendered)
        self.assertNotIn("Fuente:", rendered)

    def test_symptom_history_does_not_quote_prior_documentary_questions(self):
        notes = ["Resume la enfermedad y el tratamiento", "¿Qué cirugía tiene?", "dolor de cabeza desde ayer"]
        sources = [{"source": FILENAME, "record_id": str(UUID(int=n)), "section": "Consulta",
                    "text": f"Texto relatado o preguntado por el usuario, sin diagnóstico confirmado:\n{note}"}
                   for n, note in enumerate(notes, 1)]
        raw = json.dumps({"mode": "record_lookup", "missing_information": False,
                          "facts": [{"source": source_label(source), "quote": note} for source, note in zip(sources, notes)],
                          "guidance": "", "questions": []})
        answer = validate_rag_answer(raw, sources, "¿Qué síntomas relató en consultas anteriores?")
        self.assertIn("dolor de cabeza desde ayer", answer)
        self.assertNotIn("Resume la enfermedad", answer)
        self.assertNotIn("¿Qué cirugía tiene?", answer)

    def test_journal_indexes_only_reported_note_not_model_answers(self):
        journal = (f"\n## Consultas registradas\n\nConversaciones guardadas automáticamente.\n"
                   f"\n### Consulta {OTHER}\n\nFecha UTC: 2026-11-07T20:00:00Z\n\nModelo: ejemplo\n\n"
                   "#### Nota reportada\n> dolor de estómago\n> desde ayer\n\n"
                   "#### Respuesta sin RAG\n> Texto de IA nunca indexable\n\n"
                   "#### Respuesta con RAG\n> Otro texto IA no confirmado\n")
        parsed = parse_history(document() + journal, FILENAME)
        points = fragments_from_history(parsed)
        self.assertEqual(len(parsed["entries"]), 1)
        self.assertEqual(len(parsed["consultations"]), 1)
        self.assertEqual(len(points), 4)
        self.assertEqual(points[-1]["payload"]["section"], "Consulta")
        self.assertIn("dolor de estómago\ndesde ayer", points[-1]["payload"]["text"])
        self.assertNotIn("Texto de IA", json.dumps(points))
        self.assertNotIn("Otro texto IA", json.dumps(points))
        self.assertEqual(points[-1]["payload"]["record_id"], OTHER)

    def test_malformed_journal_is_not_silently_ignored(self):
        with self.assertRaises(ValueError):
            parse_history(document() + f"\n## Consultas registradas\n\n### Consulta {OTHER}\nIncompleta", FILENAME)


if __name__ == "__main__":
    unittest.main(verbosity=2)
