"""Contratos del corpus realista, sin red, LLM ni escrituras de datos."""

import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "python-api"))
from rag import documentary_topic_is_supported, is_record_lookup, source_label, validate_rag_answer


class RealisticCorpusContracts(unittest.TestCase):
    def answer(self, question, quote, section="Enfermedad"):
        source = {"source": "paciente-3-carla-demo.md", "record_id": "record", "section": section, "text": quote}
        raw = json.dumps({"mode": "record_lookup", "missing_information": False,
                          "facts": [{"source": source_label(source), "quote": quote}],
                          "guidance": "", "questions": []})
        return validate_rag_answer(raw, [source], question)

    def test_real_diagnosis_remains_a_documented_fact(self):
        for disease in ("enfermedad por reflujo gastroesofágico", "diabetes mellitus tipo 2", "rinitis alérgica estacional"):
            with self.subTest(disease=disease):
                quote = f"El diagnóstico registrado es {disease}."
                self.assertIn(quote, self.answer("¿Qué enfermedad está registrada?", quote))

    def test_allergy_questions_prioritize_documented_records(self):
        self.assertTrue(is_record_lookup("¿A qué es alérgica Carla?"))
        self.assertTrue(is_record_lookup("¿A qué medicamento es alérgica Carla?"))

    def test_allergic_rhinitis_is_not_a_medication_allergy(self):
        quote = "Carla tiene rinitis alérgica estacional asociada a exposición al polen."
        for question in ("¿Qué alergias a medicamentos tiene Carla?", "¿A qué medicamentos es alérgica Carla?",
                         "¿Qué alergias tiene Carla?"):
            with self.subTest(question=question):
                self.assertEqual(self.answer(question, quote), "No hay información suficiente")

    def test_environmental_allergy_does_not_answer_medication_allergy(self):
        quote = "Carla tiene alergia al polen."
        self.assertIn(quote, self.answer("¿A qué es alérgica Carla?", quote))
        self.assertEqual(self.answer("¿Qué alergias a medicamentos tiene Carla?", quote), "No hay información suficiente")

    def test_explicit_medication_allergy_can_be_reported(self):
        quote = "Consta una alergia a medicamentos: penicilina."
        self.assertIn(quote, self.answer("¿Qué alergias a medicamentos están registradas?", quote))

    def test_unrecorded_allergies_are_not_a_positive_allergy_or_its_absence(self):
        for quote in ("No se han registrado alergias a medicamentos.", "Alergias a medicamentos: desconocidas.",
                      "Sin alergias documentadas."):
            with self.subTest(quote=quote):
                self.assertEqual(self.answer("¿Qué alergias tiene Carla?", quote), "No hay información suficiente")

    def test_allergy_treatment_still_accepts_its_literal_record(self):
        quote = "Carla recibe cetirizina para la rinitis alérgica estacional."
        for question in ("¿Qué medicamento recibe para la alergia?", "¿Qué tratamiento sigue para la rinitis alérgica?"):
            with self.subTest(question=question):
                self.assertIn(quote, self.answer(question, quote, "Medicamento"))

    def test_unrecorded_dose_is_not_filled_with_a_typical_dose(self):
        for quote in ("No se ha registrado una dosis de omeprazol.", "No se han registrado dosis de metformina.",
                      "No consta la dosis de cetirizina.", "La dosis es desconocida.", "Omeprazol; sin dosis."):
            with self.subTest(quote=quote):
                self.assertEqual(self.answer("¿Qué dosis está registrada?", quote, "Medicamento"), "No hay información suficiente")

    def test_treatment_and_control_are_not_surgery(self):
        quote = "El plan incluye actividad física y un control el 2026-11-12."
        self.assertFalse(documentary_topic_is_supported("¿Cuál fue la última cirugía?", quote))

    def test_actual_corpus_preserves_the_distinction_and_missing_doses(self):
        path = Path(__file__).resolve().parents[1] / "datos/casos_clinicos.json"
        cases = json.loads(path.read_text(encoding="utf-8"))["cases"]
        carla = next(case for case in cases if case["patient_id"] == 3)
        self.assertIn("polen", self.answer("¿A qué es alérgica Carla?", carla["disease"]))
        self.assertEqual(self.answer("¿A qué medicamento es alérgica Carla?", carla["disease"]),
                         "No hay información suficiente")
        for case in cases:
            with self.subTest(patient_id=case["patient_id"]):
                self.assertEqual(self.answer("¿Qué dosis tiene registrada?", case["medication"], "Medicamento"),
                                 "No hay información suficiente")


if __name__ == "__main__":
    unittest.main(verbosity=2)
