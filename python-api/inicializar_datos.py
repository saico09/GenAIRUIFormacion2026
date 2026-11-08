"""Carga los tres pacientes demo una sola vez; conserva pacientes e informes existentes."""

import argparse
import json
from pathlib import Path
import sys

from fastapi import HTTPException
from psycopg import sql
from sqlalchemy import select, text
from sqlalchemy.exc import SQLAlchemyError

from app import clinical_store as store
from app.db import SessionLocal, initialize_database
from app.history_documents import load_histories
from app.models import MedicalConsultation, Patient
from app.schemas import PatientIn


def load_demo(data_dir: Path) -> list[tuple]:
    data = json.loads((data_dir / "pacientes.json").read_text(encoding="utf-8"))
    if not isinstance(data, list) or len(data) != 3:
        raise ValueError("La demo necesita tres pacientes, ordenados por ID 1, 2 y 3")
    rows = []
    for identifier, item in enumerate(data, start=1):
        if not isinstance(item, dict) or set(item) != {"name", "birth_date", "email"}:
            raise ValueError("Campos de paciente inválidos en la demo")
        patient = PatientIn.model_validate(item)
        if patient.name != item["name"]:
            raise ValueError("El nombre debe coincidir literalmente con el informe")
        rows.append((identifier, patient.name, patient.birth_date, str(patient.email)))
    directory = data_dir / "historias"
    if directory.exists() and list(directory.glob("paciente-*.md")):
        seen = set()
        for history in load_histories(directory):
            if history["patient_id"] not in (1, 2, 3):
                raise ValueError("Hay informes ajenos a la demo; no se asignaron identidades")
            name = rows[history["patient_id"] - 1][1]
            if history["markdown"].splitlines()[0] != f"# Historia clínica ficticia — {name}":
                raise ValueError("El nombre del informe no corresponde al paciente de la demo")
            if history["consultations"]:
                raise ValueError("No se importa un diario clínico sin su respaldo SQL")
            for entry in history["entries"]:
                if entry["id"] in seen:
                    raise ValueError("Los UUID no pueden repetirse entre informes")
                seen.add(entry["id"])
    return rows


def initialize_demo(data_dir: Path) -> dict:
    initialize_database()
    previous_directory = store.DIRECTORY
    store.DIRECTORY = (data_dir / "historias").absolute()
    try:
        with SessionLocal() as db, store.clinical_transaction(db) as changes:
            existing = list(db.scalars(select(Patient).order_by(Patient.id)))
            if existing:
                return {"status": "conservados", "patients": len(existing), "inserted": 0}
            if db.scalars(select(MedicalConsultation.id).limit(1)).first() is not None:
                raise ValueError("La base conserva historial previo; no se recrearon pacientes borrados")
            rows = load_demo(data_dir)
            sequence = db.execute(text("""
                SELECT n.nspname,c.relname,s.seqincrement,s.seqcycle
                FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
                JOIN pg_sequence s ON s.seqrelid=c.oid
                WHERE c.oid=pg_get_serial_sequence('public.patients','id')::regclass
            """)).one()
            if tuple(sequence[2:]) != (1, False):
                raise ValueError("La secuencia debe ser una identidad incremental")
            identifier = sql.Identifier(sequence[0], sequence[1])
            connection = db.connection()
            last, called = connection.exec_driver_sql(
                sql.SQL("SELECT last_value,is_called FROM {}").format(identifier).as_string()
            ).one()
            next_id = max(4, last + int(called))
            connection.exec_driver_sql(sql.SQL("ALTER SEQUENCE {} RESTART WITH {}").format(
                identifier, sql.Literal(next_id)).as_string())
            for identifier, name, born, email in rows:
                patient = Patient(id=identifier, name=name, birth_date=born, email=email)
                db.add(patient)
                db.flush()
                store.load(db, patient, changes)
        return {"status": "inicializados", "patients": 3, "inserted": 3, "ids": [1, 2, 3], "next_id": next_id}
    finally:
        store.DIRECTORY = previous_directory


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=Path("/datos"))
    args = parser.parse_args()
    try:
        result = initialize_demo(args.data_dir)
    except (SQLAlchemyError, OSError, ValueError, KeyError, HTTPException) as error:
        print(json.dumps({"status": "error", "error_type": type(error).__name__,
                          "sqlstate": getattr(getattr(error, "orig", None), "sqlstate", None),
                          "message": "No se cargó la demo; comprueba pacientes, informes y PostgreSQL."}), file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
