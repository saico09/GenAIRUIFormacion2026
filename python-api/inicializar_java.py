"""Carga controlada de la demo: asocia los informes existentes a Java, solo en una tabla vacía."""

import argparse
import json
import os
from pathlib import Path
import sys

import psycopg
from psycopg import sql

from app.history_documents import load_histories
from app.schemas import PatientIn


def load_demo(data_dir: Path) -> list[tuple]:
    data = json.loads((data_dir / "pacientes.json").read_text(encoding="utf-8"))
    if not isinstance(data, list) or len(data) != 3:
        raise ValueError("La demo necesita exactamente tres pacientes, ordenados por ID 1, 2 y 3")
    rows = []
    for identifier, item in enumerate(data, start=1):
        if not isinstance(item, dict) or set(item) != {"name", "birth_date", "email"}:
            raise ValueError("Campos de paciente inválidos en la demo")
        patient = PatientIn.model_validate(item)
        if patient.name != item["name"] or any(ord(char) < 32 or ord(char) == 127 for char in patient.name):
            raise ValueError("El nombre de la demo debe coincidir literalmente con su informe")
        rows.append((identifier, patient.name, patient.birth_date, str(patient.email)))

    histories = load_histories(data_dir / "historias")
    if {history["patient_id"] for history in histories} != {1, 2, 3}:
        raise ValueError("Los informes de la demo deben corresponder exactamente a los IDs 1, 2 y 3")
    seen = set()
    for history in histories:
        name = rows[history["patient_id"] - 1][1]
        if history["markdown"].splitlines()[0] != f"# Historia clínica ficticia — {name}":
            raise ValueError("El nombre del informe no corresponde al paciente de la demo")
        if not history["entries"]:
            raise ValueError("Cada informe de la demo necesita al menos un registro con UUID")
        for entry in history["entries"]:
            if entry["id"] in seen:
                raise ValueError("Los UUID de la demo no pueden repetirse entre informes")
            seen.add(entry["id"])
    return rows


def initialize_demo(data_dir: Path) -> dict:
    with psycopg.connect(
        host=os.environ["POSTGRES_HOST"], port=os.environ.get("POSTGRES_PORT", "5432"),
        dbname=os.environ["POSTGRES_DB"], user=os.environ["POSTGRES_USER"],
        password=os.environ["POSTGRES_PASSWORD"], connect_timeout=5,
    ) as connection:
        connection.execute("SET LOCAL lock_timeout = '10s'")
        connection.execute("SET LOCAL statement_timeout = '30s'")
        # Serializa esta carga con INSERT/UPDATE/DELETE y otras cargas; permite las lecturas.
        connection.execute("LOCK TABLE java.patients IN SHARE ROW EXCLUSIVE MODE")
        count = connection.execute("SELECT count(*) FROM java.patients").fetchone()[0]
        if count:
            # No validar ni reinterpretar una demo que el usuario ya pudo haber editado.
            return {"status": "conservados", "patients": count, "inserted": 0}

        rows = load_demo(data_dir)  # Toda la validación precede a la primera escritura.
        sequence = connection.execute("""
            SELECT n.nspname, c.relname, s.seqincrement, s.seqcycle
            FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
            JOIN pg_sequence s ON s.seqrelid = c.oid
            WHERE c.oid = pg_get_serial_sequence('java.patients', 'id')::regclass
        """).fetchone()
        if sequence is None or sequence[2:] != (1, False):
            raise ValueError("La secuencia debe ser la identidad incremental de java.patients")
        identifier = sql.Identifier(sequence[0], sequence[1])
        last, called = connection.execute(
            sql.SQL("SELECT last_value, is_called FROM {}").format(identifier)
        ).fetchone()
        next_id = max(4, last + int(called))
        # RESTART es transaccional, a diferencia de setval: también se revierte si falla la carga.
        connection.execute(sql.SQL("ALTER SEQUENCE {} RESTART WITH {}").format(identifier, sql.Literal(next_id)))
        with connection.cursor() as cursor:
            cursor.executemany("INSERT INTO java.patients (id, name, birth_date, email) VALUES (%s, %s, %s, %s)", rows)
    return {"status": "inicializados", "patients": 3, "inserted": 3, "ids": [1, 2, 3], "next_id": next_id}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=Path("/datos"))
    args = parser.parse_args()
    try:
        result = initialize_demo(args.data_dir)
    except (psycopg.Error, OSError, ValueError, KeyError) as error:
        # No mostrar conninfo, filas, notas clínicas ni mensajes SQL con parámetros.
        print(json.dumps({"status": "error", "error_type": type(error).__name__,
                          "sqlstate": getattr(error, "sqlstate", None),
                          "message": "No se inicializó la demo; comprueba PostgreSQL y los tres pacientes/informes."}), file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
