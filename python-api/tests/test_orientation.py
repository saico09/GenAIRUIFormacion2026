"""Esquema, evidencia y render compartidos; sin red ni evaluación clínica simulada."""
from copy import deepcopy
import json
import re
import unittest

from orientation import orientation_schema, render_orientation
from rag import direct_response_schema, validate_direct_answer, validate_rag_answer


def guidance():
    return {"possibilities": [{"cause": "posibilidad A", "condition": "condición A"},
                              {"cause": "posibilidad B", "condition": "condición B"}],
            "optional_details": ["localización exacta", "duración"], "current_alert": None}


class OrientationTests(unittest.TestCase):
    def test_both_modes_render_conditions_and_optional_details_without_free_narrative(self):
        direct = json.dumps({"mode": "symptom_guidance", "guidance": guidance()})
        rag = json.dumps({"mode": "symptom_guidance", "guidance": guidance(),
                          "missing_information": True, "facts": [], "questions": []})
        for answer in (validate_direct_answer(direct, "dolor localizado"),
                       validate_rag_answer(rag, [], "dolor localizado")):
            self.assertIn("Podría ser posibilidad A si además hubiera condición A.", answer)
            self.assertIn("Podría ser posibilidad B si además hubiera condición B.", answer)
            self.assertIn("Para afinar la orientación, puedes añadir: localización exacta; duración.", answer)
            self.assertNotIn("?", answer)

    def test_schema_and_validator_reject_questions_controls_and_fake_citations(self):
        properties = orientation_schema()["properties"]
        pattern = properties["optional_details"]["items"]["pattern"]
        for text in ("¿Dónde duele?", "Lugar?", "dato\notro", "dato\t", "dato[fuente]", "dato\x00"):
            with self.subTest(text=text):
                self.assertIsNone(re.fullmatch(pattern, text))
                value = guidance()
                value["optional_details"][0] = text
                with self.assertRaises(ValueError):
                    render_orientation(value, "relato")

    def test_rejects_bad_types_missing_extra_fields_and_limits(self):
        invalid = [None, "narración libre", {**guidance(), "narrative": "dato inventado"}]
        for field, value in (("possibilities", {}), ("possibilities", [guidance()["possibilities"][0]] * 4),
                             ("possibilities", [{"cause": "A", "condition": "B", "extra": "C"}]),
                             ("optional_details", ["un solo detalle"]), ("optional_details", ["x" * 121, "dato"]),
                             ("current_alert", 42)):
            invalid.append({**guidance(), field: value})
        for value in invalid:
            with self.subTest(value=value), self.assertRaises(ValueError):
                render_orientation(value, "relato")

    def test_empty_possibilities_for_vague_input_do_not_invent_a_diagnosis(self):
        value = {**guidance(), "possibilities": []}
        answer = render_orientation(value, "me siento mal")
        self.assertIn("no permite priorizar una causa", answer)
        self.assertNotIn("Podría ser", answer)
        value["possibilities"] = guidance()["possibilities"][:1]
        self.assertEqual(render_orientation(value, "relato").count("Podría ser"), 1)

    def test_current_alert_requires_literal_non_negative_non_hypothetical_evidence(self):
        for question, quote in (("Vomito sangre ahora.", "sangrado digestivo"),
                                ("No estoy vomitando sangre.", "vomitando sangre"),
                                ("Si vomitara sangre buscaría ayuda.", "vomitara sangre"),
                                ("Me duele la cabeza.", "una alarma sólo presente en el historial")):
            with self.subTest(question=question), self.assertRaises(ValueError):
                render_orientation({**guidance(), "current_alert": quote}, question)

    def test_alert_schema_offers_only_complete_literal_phrases(self):
        question = "No vomito sangre, aunque me siento cansada. Me duele la cabeza."
        quotes = orientation_schema(question)["properties"]["current_alert"]["enum"]
        self.assertIn(None, quotes)
        self.assertNotIn("No vomito sangre, aunque me siento cansada", quotes)
        self.assertIn("Me duele la cabeza", quotes)
        self.assertNotIn("vomito sangre", quotes)
        self.assertTrue(all(quote is None or quote in question for quote in quotes))
        long_sentence = "No " + "dato " * 60 + "vomito sangre"
        self.assertEqual(orientation_schema(long_sentence)["properties"]["current_alert"]["enum"], [None])

    def test_complete_negative_and_conditional_quotes_cannot_bypass_with_punctuation(self):
        for question in ("No estoy vomitando sangre.", "Si vomitara sangre buscaría ayuda.",
                         "No estoy vomitando sangre;", "No estoy vomitando sangre. Me siento cansada.",
                         "Estoy vomitando sangre ahora y no tengo fiebre."):
            for quote in (question, question.rstrip(".;")):
                with self.subTest(question=question, quote=quote):
                    self.assertNotIn(quote, orientation_schema(question)["properties"]["current_alert"]["enum"])
                    with self.assertRaises(ValueError):
                        render_orientation({**guidance(), "current_alert": quote}, question)

    def test_affirmative_sentence_and_combined_quote_keep_urgent_action(self):
        for question, quote in (("Estoy vomitando sangre ahora.", "Estoy vomitando sangre ahora."),
                                ("Estoy vomitando sangre ahora. Me siento mareada.", "Estoy vomitando sangre ahora. Me siento mareada."),
                                ("No tengo fiebre. Estoy vomitando sangre ahora.", "Estoy vomitando sangre ahora")):
            with self.subTest(question=question):
                self.assertIn(quote, orientation_schema(question)["properties"]["current_alert"]["enum"])
                self.assertTrue(render_orientation({**guidance(), "current_alert": quote}, question).startswith("Busca atención urgente"))

    def test_current_alert_can_coexist_with_a_different_negated_fact(self):
        for question in ("No tengo fiebre, pero estoy vomitando sangre ahora.",
                         "Estoy vomitando sangre ahora y no tengo fiebre."):
            quote = "vomitando sangre ahora"
            answer = render_orientation({**guidance(), "current_alert": quote}, question)
            self.assertTrue(answer.startswith("Busca atención urgente"))
            self.assertIn(quote, answer)

    def test_direct_documentary_request_retains_lack_of_history(self):
        raw = json.dumps({"mode": "record_lookup", "guidance": None})
        question = "¿Qué cirugía consta en mi historia?"
        self.assertIn("No tengo acceso al historial", validate_direct_answer(raw, question))
        self.assertTrue(any(variant["properties"]["mode"]["enum"] == ["record_lookup"]
                            for variant in direct_response_schema(question)["anyOf"]))

    def test_legacy_guidance_is_explicit_and_not_enabled_by_runtime(self):
        raw = json.dumps({"mode": "symptom_guidance", "guidance": "Texto histórico sin modificar",
                          "missing_information": True, "facts": [], "questions": []})
        with self.assertRaises(ValueError):
            validate_rag_answer(raw, [], "dolor")
        self.assertIn("Texto histórico sin modificar", validate_rag_answer(raw, [], "dolor", allow_legacy_guidance=True))


if __name__ == "__main__":
    unittest.main()
