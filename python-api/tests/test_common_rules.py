"""Mismos vectores que java-api CommonRulesTest: ambas APIs deben coincidir."""

from datetime import date, timedelta
import unicodedata
import unittest

from pydantic import ValidationError

from app.schemas import (EDGE, ChatIn, ClinicalProposalIn, DiseaseIn, PatientIn, clinical, normalize_email,
                         patient_id, record_id, trim)

EMOJI = "\U0001F600"
BIRTH = "1990-01-02"


def invalid_fields(**values) -> set[str]:
    data = {"name": "Ana", "birth_date": BIRTH, "email": "ana@example.com", **values}
    try:
        PatientIn.model_validate(data)
    except ValidationError as error:
        return {".".join(str(part) for part in item["loc"]) for item in error.errors()}
    return set()


class RouteIdsR1(unittest.TestCase):
    def test_patient_ids_only_decimal_digits_in_range(self):
        self.assertEqual(patient_id("1"), 1)
        self.assertEqual(patient_id("01"), 1)
        self.assertEqual(patient_id("2147483647"), 2147483647)
        for value in ("0", "-1", "abc", "0x1", "1e3", "2147483648", "99999999999", "", " 1", "١", "+1", "1.0"):
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, "entre 1 y 2147483647"):
                patient_id(value)

    def test_record_uuid_is_case_insensitive_and_canonical(self):
        self.assertEqual(record_id("6EC12D52-872C-4D82-A6B8-235CBD99936C", "disease_id"),
                         "6ec12d52-872c-4d82-a6b8-235cbd99936c")
        for value in ("no-uuid", "6ec12d52872c4d82a6b8235cbd99936c", "{6ec12d52-872c-4d82-a6b8-235cbd99936c}",
                      "urn:uuid:6ec12d52-872c-4d82-a6b8-235cbd99936c"):
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, "disease_id debe ser un UUID"):
                record_id(value, "disease_id")


class PatientR2R7(unittest.TestCase):
    def test_trim_is_space_tab_lf_cr_and_zs_only(self):
        self.assertEqual(set(EDGE), {" ", "\t", "\n", "\r"} | {
            chr(code) for code in range(0x110000) if unicodedata.category(chr(code)) == "Zs"})
        self.assertEqual(trim("\u00a0\u3000 Ana \t\r\n"), "Ana")
        # Otros espacios Unicode no se recortan: son controles o separadores y se rechazan después.
        self.assertEqual(trim("\x0bAna\u2028"), "\x0bAna\u2028")

    def test_names_follow_r2_r3_r4(self):
        for value, expected in {"  Ana  ": "Ana", "Ana\u00a0": "Ana", EMOJI * 200: EMOJI * 200,
                                "José Núñez": "José Núñez"}.items():
            with self.subTest(value=value[:10]):
                self.assertEqual(PatientIn(name=value, birth_date=BIRTH, email="ana@example.com").name, expected)
        for value in ("\u00a0", EMOJI * 201, "Ana\u202eX", "Ana\u2028Demo", "Ana\tDemo", "", "Ana\x00", "Ana\ud800",
                      "Ana\u200bDemo", "Ana\x85"):
            with self.subTest(value=value[:10]):
                self.assertEqual(invalid_fields(name=value), {"name"})

    def test_emails_follow_r6(self):
        for value, expected in {"Ana@Example.COM": "Ana@example.com", " ana@ex.com ": "ana@ex.com",
                                "ana+tag@ex.com": "ana+tag@ex.com", "ana@ejemplo.españa": "ana@ejemplo.españa",
                                "ana@x.test": "ana@x.test"}.items():
            with self.subTest(value=value):
                self.assertEqual(normalize_email(value), expected)
        for value in ("ana@localhost", "ana@[127.0.0.1]", "ana@127.0.0.1", "a\x81b@example.com", "ana@exa mple.com",
                      "ana@ex\u200b.com", "a" * 250 + "@ex.com", "Ana <ana@example.com>", "a@b@c.com", "@ex.com",
                      "a..b@ex.com", "ana@-ex.com", "ana@.com", "a" * 65 + "@ex.com"):
            with self.subTest(value=value[:20]):
                self.assertEqual(invalid_fields(email=value), {"email"})

    def test_birth_dates_follow_r7(self):
        today = date.today()
        self.assertEqual(PatientIn(name="Ana", birth_date=today.isoformat(), email="a@ex.com").birth_date, today)
        self.assertEqual(PatientIn(name="Ana", birth_date="2024-02-29", email="a@ex.com").birth_date, date(2024, 2, 29))
        for value in ((today + timedelta(days=1)).isoformat(), "0000-01-01", "1990-02-30", "1990-1-02", "02-01-1990",
                      "١٩٩٠-٠١-٠٢", 19900102, None):
            with self.subTest(value=value):
                self.assertEqual(invalid_fields(birth_date=value), {"birth_date"})

    def test_messages_match_java_without_pydantic_prefix(self):
        with self.assertRaises(ValidationError) as raised:
            PatientIn(name="\u00a0", birth_date="2999-01-01", email="ana@localhost")
        messages = {item["loc"][0]: item["msg"] for item in raised.exception.errors()}
        self.assertEqual(messages["birth_date"], "La fecha de nacimiento no puede ser posterior a hoy")
        self.assertTrue(messages["name"].startswith("Usa entre 1 y 200 caracteres"))
        self.assertTrue(messages["email"].startswith("Usa nombre@dominio.tld"))


class ClinicalR2R5(unittest.TestCase):
    def test_clinical_fields(self):
        self.assertEqual(clinical("Reflujo"), "Reflujo")
        self.assertEqual(clinical("  Reflujo \t"), "Reflujo")
        self.assertEqual(clinical("Texto #hashtag"), "Texto #hashtag")
        self.assertEqual(clinical("\u00a0"), "")
        self.assertEqual(clinical("No registrado."), "")
        self.assertEqual(clinical("Línea 1\r\nLínea 2\r"), "Línea 1\nLínea 2")
        self.assertEqual(len(clinical(EMOJI * 2000)), 2000)
        self.assertEqual(clinical("#\u00a0no es encabezado"), "#\u00a0no es encabezado")
        for value in ("Reflujo\u2028# nota", "# Titulo", "Linea 1\n## Sub", "Re\u200bflujo", EMOJI * 2001, "Dato\x00",
                      "Dato\ud800", "Linea\r# Titulo", "####### siete\n###### seis", "Dato\x0b"):
            with self.subTest(value=value[:12]), self.assertRaises(ValueError):
                clinical(value)

    def test_disease_messages_use_json_field_names(self):
        with self.assertRaises(ValidationError) as raised:
            DiseaseIn(disease="Dato\x00", treatment="# Título", medication="ok")
        errors = {item["loc"][0]: item["msg"] for item in raised.exception.errors()}
        self.assertEqual(errors, {"disease": "no admite caracteres de control, de formato ni separadores Unicode",
                                  "treatment": "ninguna línea puede empezar como encabezado Markdown (#)"})
        with self.assertRaises(ValidationError) as raised:
            DiseaseIn(disease="\u00a0", treatment="No registrado.", medication="")
        self.assertEqual(raised.exception.errors()[0]["msg"], "Un registro necesita al menos un campo con información")


class FreeTextR3(unittest.TestCase):
    def test_question_keeps_text_and_rejects_controls_except_line_breaks(self):
        self.assertEqual(ChatIn(patient_id=1, question=" dolor\r\n\tagudo ").question, " dolor\r\n\tagudo ")
        for question in ("dolor\x00", "dolor\x1b", "dolor\ud800", "\u00a0 "):
            with self.subTest(question=question), self.assertRaises(ValidationError):
                ChatIn(patient_id=1, question=question)

    def test_body_patient_ids_are_strict_and_bounded(self):
        for value in (0, -1, 2147483648, True, "1", 1.0):
            with self.subTest(value=value), self.assertRaises(ValidationError):
                ClinicalProposalIn(patient_id=value, note="nota")
        self.assertEqual(ChatIn(patient_id=2147483647, question="hola").patient_id, 2147483647)


if __name__ == "__main__":
    unittest.main()
