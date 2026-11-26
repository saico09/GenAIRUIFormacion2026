"""El esquema de arranque sólo crea lo que falta y Java empaqueta la misma copia."""

from pathlib import Path
import re
import unittest

APP = Path(__file__).resolve().parents[1] / "app" / "schema.sql"
JAVA = Path(__file__).resolve().parents[2] / "java-api" / "src" / "main" / "resources" / "schema.sql"
MIGRATION = Path(__file__).resolve().parents[2] / "database" / "migrations" / "001_unified_clinical.sql"


# Única excepción al DDL idempotente: detener el arranque sobre un volumen del modelo anterior.
GUARD = re.compile(r"DO \$guard\$.*?\$guard\$;", re.S)


def statements(path: Path) -> list[str]:
    sql = "\n".join(line for line in path.read_text(encoding="utf-8").splitlines() if not line.lstrip().startswith("--"))
    return [" ".join(part.split()) for part in GUARD.sub("", sql).split(";") if part.strip()]


class RuntimeSchema(unittest.TestCase):
    def test_only_idempotent_ddl_of_the_current_model(self):
        allowed = re.compile(r"^(BEGIN|COMMIT|SELECT pg_advisory_xact_lock\(71420261107\)|CREATE TABLE IF NOT EXISTS public\.\w+ \(.*\)"
                             r"|CREATE INDEX IF NOT EXISTS \w+ ON public\.\w+\(.*\)|ALTER TABLE public\.\w+ ADD COLUMN IF NOT EXISTS .*)$")
        for statement in statements(APP):
            with self.subTest(statement=statement[:60]):
                self.assertRegex(statement, allowed)
                # DELETE no se busca porque "ON DELETE CASCADE" es parte de la FK.
                self.assertNotRegex(statement.upper(), r"\b(UPDATE|DROP|INSERT|RENAME|TRUNCATE)\b|SET SCHEMA|JAVA\.|^DO\b")
        tables = re.findall(r"CREATE TABLE IF NOT EXISTS public\.(\w+)", APP.read_text(encoding="utf-8"))
        self.assertEqual(tables, ["patients", "patient_diseases", "medical_consultations", "transaction_logs"])

    def test_old_volume_stops_startup_without_changing_it(self):
        guards = GUARD.findall(APP.read_text(encoding="utf-8"))
        self.assertEqual(len(guards), 1)
        self.assertIn("to_regclass('java.patients')", guards[0])
        self.assertIn("RAISE EXCEPTION", guards[0])
        self.assertNotRegex(guards[0].upper(), r"\b(UPDATE|DROP|INSERT|RENAME|TRUNCATE|CREATE|ALTER)\b")

    @unittest.skipUnless(JAVA.exists(), "Ejecutar con el repositorio completo montado para comparar la copia de Java")
    def test_java_copy_is_byte_identical(self):
        self.assertEqual(JAVA.read_bytes(), APP.read_bytes())

    @unittest.skipUnless(MIGRATION.exists(), "Ejecutar con el repositorio completo montado para revisar la migración")
    def test_historical_migration_is_kept_and_marked_manual(self):
        text = MIGRATION.read_text(encoding="utf-8")
        self.assertTrue(text.startswith("-- MIGRACIÓN MANUAL E HISTÓRICA"))
        for fragment in ("java.patients", "DROP COLUMN IF EXISTS execution_id", "UPDATE public.transaction_logs"):
            self.assertIn(fragment, text)


if __name__ == "__main__":
    unittest.main()
