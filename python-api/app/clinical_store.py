"""Pacientes y registros compartidos: SQL relacionado y proyección Markdown.

Funciona sin Java, Ollama ni Qdrant. Ambas APIs toman la misma llave PostgreSQL
antes de leer/modificar un informe. Los errores normales restauran los archivos;
SQL y filesystem no constituyen una transacción distribuida ante un cierre forzado.
"""

from contextlib import contextmanager
from datetime import timezone
import hashlib
import os
from pathlib import Path
import re
import tempfile
import unicodedata
from uuid import UUID, uuid4

from fastapi import HTTPException
from sqlalchemy import delete, select, text
from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.history_documents import parse_history, UNRECORDED
from app.models import MedicalConsultation, Patient, PatientDisease
from app.observability import execution_id_context, log_event
from app.schemas import DiseaseIn, PatientIn

CLINICAL_LOCK = 71420261109
DIRECTORY = Path(os.getenv("HISTORY_DIR", "/datos/historias")).absolute()
JOURNAL_HEADING = "\n## Consultas registradas\n"
MAX_BYTES = 1048576


def require_shared_history():
    """En Minikube, falla antes de usar una carpeta sin el montaje compartido."""
    marker = os.getenv("HISTORY_SHARED_MARKER")
    if not marker:
        return
    try:
        path = Path(marker)
        if path.is_symlink() or path.read_text(encoding="utf-8").strip() != "genai-historias-v1":
            raise OSError("Marcador no válido")
    except (OSError, UnicodeError) as error:
        raise HTTPException(status_code=503, detail="El montaje compartido de historias no está disponible; ejecuta scripts/reanudar_minikube.ps1") from error


def invalid(message: str):
    return HTTPException(status_code=422, detail=message)


def conflict(message: str):
    return HTTPException(status_code=409, detail=message)


def revision(markdown: str) -> str:
    return hashlib.sha256(markdown.encode("utf-8")).hexdigest()


def filename(patient: Patient) -> Path:
    plain = "".join(char for char in unicodedata.normalize("NFD", patient.name)
                    if not unicodedata.category(char).startswith("M"))
    slug = re.sub(r"[^a-z0-9]+", "-", plain.lower()).strip("-")[:80].rstrip("-") or "paciente"
    return DIRECTORY / f"paciente-{patient.id}-{slug}.md"


def header(patient: Patient) -> str:
    return (f"# Historia clínica ficticia — {patient.name}\n\nDatos ficticios para la formación."
            f"\n\npatient_id: {patient.id}\n")


def render(patient: Patient, entries: list[dict], journal: str) -> str:
    markdown = header(patient)
    for entry in entries:
        markdown += (f"\n## Registro {entry['id']}\n\n### Enfermedad\n{entry['disease'] or UNRECORDED}"
                     f"\n\n### Tratamiento\n{entry['treatment'] or UNRECORDED}"
                     f"\n\n### Medicamento\n{entry['medication'] or UNRECORDED}\n")
    return markdown + journal


def render_journal(db: Session, patient_id: int) -> str:
    rows = db.scalars(select(MedicalConsultation).where(
        MedicalConsultation.patient_id == patient_id, MedicalConsultation.kind == "consultation"
    ).order_by(MedicalConsultation.storage_order)).all()
    if not rows:
        return ""
    result = (JOURNAL_HEADING + "\nConversaciones guardadas automáticamente. La nota describe lo reportado; "
              "las respuestas de IA no son diagnósticos confirmados.\n")
    for row in rows:
        instant = row.created_at.astimezone(timezone.utc)
        # Instant.toString de Java utiliza grupos de tres decimales.
        decimals = (f".{instant.microsecond:06d}" if instant.microsecond % 1000
                    else f".{instant.microsecond // 1000:03d}" if instant.microsecond else "")
        created = instant.strftime("%Y-%m-%dT%H:%M:%S") + decimals + "Z"
        result += f"\n### Consulta {row.id}\n\nFecha UTC: {created}\n\nModelo: {row.model}\n"
        for title, value in (("Nota reportada", row.question), ("Respuesta sin RAG", row.direct_answer),
                             ("Respuesta con RAG", row.rag_answer)):
            quoted = "> " + value.replace("\r\n", "\n").replace("\r", "\n").replace("\n", "\n> ")
            result += f"\n#### {title}\n{quoted}\n"
    return result


def find_file(patient_id: int) -> Path | None:
    require_shared_history()
    DIRECTORY.mkdir(parents=True, exist_ok=True)
    paths = [path for path in DIRECTORY.glob(f"paciente-{patient_id}-*.md")
             if re.fullmatch(rf"paciente-{patient_id}-[a-z0-9-]+\.md", path.name)]
    if len(paths) > 1:
        raise conflict("Hay más de un informe para el mismo paciente; no se sobrescribió ninguno")
    if paths and (paths[0].is_symlink() or not paths[0].is_file()):
        raise conflict("El informe no es un archivo regular")
    return paths[0] if paths else None


def read(path: Path) -> str:
    require_shared_history()
    if path.stat().st_size > MAX_BYTES:
        raise invalid("El Markdown admite como máximo 1 MiB UTF-8")
    return path.read_bytes().decode("utf-8")


def atomic_write(path: Path, content: bytes):
    require_shared_history()
    if len(content) > MAX_BYTES:
        raise invalid("El Markdown admite como máximo 1 MiB UTF-8")
    DIRECTORY.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=".history-", suffix=".tmp", dir=DIRECTORY)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(content)
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


class FileChanges:
    def __init__(self):
        self.previous: dict[Path, bytes | None] = {}

    def remember(self, path: Path):
        if path not in self.previous:
            if path.is_symlink():
                raise conflict("El informe no es un archivo regular")
            self.previous[path] = path.read_bytes() if path.exists() else None

    def write(self, path: Path, markdown: str):
        self.remember(path)
        atomic_write(path, markdown.encode("utf-8"))

    def remove(self, path: Path):
        require_shared_history()
        self.remember(path)
        path.unlink()

    def restore(self):
        for path, content in self.previous.items():
            if content is None:
                path.unlink(missing_ok=True)
            else:
                atomic_write(path, content)


@contextmanager
def clinical_transaction(db: Session):
    changes = FileChanges()
    previous_bind = db.get_bind()
    # Mantener esta conexión fuera de Session evita devolver al pool una conexión
    # con un bloqueo de sesión. El lock sobrevive al rollback/commit fallido para
    # compensar antes de permitir escrituras de la otra API.
    with previous_bind.connect() as connection:
        db.bind = connection
        locked = False
        try:
            try:
                with db.begin():
                    db.execute(text("SELECT pg_advisory_lock(:key)"), {"key": CLINICAL_LOCK})
                    locked = True
                    db.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": CLINICAL_LOCK})
                    yield changes
                    db.flush()
            except Exception as error:
                try:
                    changes.restore()
                except Exception as recovery:
                    log_event("history_recovery", status="error", error_type=type(recovery).__name__)
                    error.add_note("No se pudo restaurar el archivo tras el error; revisar el respaldo SQL")
                if isinstance(error, (OSError, UnicodeError)):
                    raise HTTPException(status_code=503, detail="No se pudo leer o guardar el informe Markdown") from error
                raise
        finally:
            try:
                if locked and not connection.invalidated:
                    connection.execute(text("SELECT pg_advisory_unlock(:key)"), {"key": CLINICAL_LOCK})
                    connection.commit()
            except Exception as error:
                # Una conexión que no pudo liberar su lock nunca vuelve al pool.
                connection.invalidate()
                log_event("history_unlock", status="error", error_type=type(error).__name__)
            finally:
                db.bind = previous_bind


def patient_or_404(db: Session, patient_id: int) -> Patient:
    patient = db.get(Patient, patient_id)
    if patient is None:
        raise HTTPException(status_code=404, detail="Paciente no encontrado")
    return patient


def latest_backup(db: Session, patient_id: int):
    return db.scalars(select(MedicalConsultation).where(MedicalConsultation.patient_id == patient_id)
                      .order_by(MedicalConsultation.storage_order.desc()).limit(1)).first()


def snapshot(db: Session, patient: Patient, path: Path, markdown: str, kind="snapshot"):
    previous = latest_backup(db, patient.id)
    digest = revision(markdown)
    if (kind != "deleted" and previous is not None and previous.revision == digest
            and previous.filename == path.name):
        return
    identifier = execution_id_context.get()
    db.add(MedicalConsultation(id=uuid4(), execution_id=UUID(identifier) if identifier else uuid4(),
                              patient_id=patient.id, kind=kind, filename=path.name,
                              markdown_content=markdown, revision=digest, sources=[]))


def sync_entries(db: Session, patient_id: int, entries: list[dict]):
    identifiers = [UUID(entry["id"]) for entry in entries]
    db.execute(delete(PatientDisease).where(PatientDisease.patient_id == patient_id,
                                           PatientDisease.id.not_in(identifiers)))
    for entry, identifier in zip(entries, identifiers, strict=True):
        row = db.get(PatientDisease, identifier)
        if row is not None and row.patient_id != patient_id:
            raise conflict("El UUID de un registro pertenece a otro paciente")
        if row is None:
            row = PatientDisease(id=identifier, patient_id=patient_id)
            db.add(row)
        for field in ("disease", "treatment", "medication"):
            setattr(row, field, entry[field])
    db.flush()


def load(db: Session, patient: Patient, changes: FileChanges):
    path = find_file(patient.id)
    journal = render_journal(db, patient.id)
    if path is None:
        path = filename(patient)
        backup = latest_backup(db, patient.id)
        if backup is not None:
            if revision(backup.markdown_content) != backup.revision:
                raise conflict("El respaldo del informe no supera la comprobación de integridad")
            markdown = backup.markdown_content
        else:
            entries = [disease_response(row) for row in db.scalars(select(PatientDisease).where(
                PatientDisease.patient_id == patient.id).order_by(PatientDisease.id))]
            markdown = render(patient, entries, journal)
        changes.write(path, markdown)
    else:
        markdown = read(path)
    normalized = markdown.replace("\r\n", "\n")
    if not normalized.startswith(header(patient)):
        raise conflict("El título y patient_id deben conservar el propietario del informe")
    _, separator, actual_journal = normalized.partition(JOURNAL_HEADING)
    if (separator + actual_journal if separator else "") != journal:
        raise conflict("Las consultas automáticas son históricas; conserva su contenido")
    try:
        history = parse_history(markdown, path.name)
        for entry in history["entries"]:
            DiseaseIn.model_validate(entry)
    except ValueError as error:
        raise invalid(str(error)) from error
    sync_entries(db, patient.id, history["entries"])
    snapshot(db, patient, path, markdown)
    return path, history["entries"], journal


def save(db: Session, patient: Patient, path: Path, entries: list[dict], journal: str, changes: FileChanges):
    if len(entries) > 50:
        raise invalid("La historia admite como máximo 50 registros")
    markdown = render(patient, entries, journal)
    sync_entries(db, patient.id, entries)
    changes.write(path, markdown)
    snapshot(db, patient, path, markdown)


def bootstrap_histories():
    with SessionLocal() as db:
        ids = list(db.scalars(select(Patient.id).order_by(Patient.id)))
    for patient_id in ids:
        try:
            with SessionLocal() as db, clinical_transaction(db) as changes:
                load(db, patient_or_404(db, patient_id), changes)
        except Exception as error:
            log_event("history_backup", patient_id=patient_id, status="error", error_type=type(error).__name__)


def create_patient(db: Session, data: PatientIn):
    with clinical_transaction(db) as changes:
        patient = Patient(**data.model_dump())
        db.add(patient)
        db.flush()
        if find_file(patient.id) is not None:
            raise conflict("Ya existe un informe para este ID")
        save(db, patient, filename(patient), [], "", changes)
    return patient


def update_patient(db: Session, patient_id: int, data: PatientIn):
    with clinical_transaction(db) as changes:
        patient = patient_or_404(db, patient_id)
        old_path, entries, journal = load(db, patient, changes)
        for field, value in data.model_dump().items():
            setattr(patient, field, value)
        new_path = filename(patient)
        if new_path != old_path and new_path.exists():
            raise conflict("Ya existe otro archivo con el nombre nuevo")
        save(db, patient, new_path, entries, journal, changes)
        if new_path != old_path:
            changes.remove(old_path)
    return patient


def delete_patient(db: Session, patient_id: int):
    with clinical_transaction(db) as changes:
        patient = patient_or_404(db, patient_id)
        path, _, _ = load(db, patient, changes)
        snapshot(db, patient, path, read(path), "deleted")
        db.delete(patient)
        db.flush()
        changes.remove(path)


def disease_response(row):
    return {"id": str(row.id), "patient_id": row.patient_id, "disease": row.disease,
            "treatment": row.treatment, "medication": row.medication}


def diseases(db: Session, patient_id: int, identifier: UUID | None = None):
    with clinical_transaction(db) as changes:
        _, entries, _ = load(db, patient_or_404(db, patient_id), changes)
        result = [{**entry, "patient_id": patient_id} for entry in entries]
        if identifier is None:
            return result
        return next((entry for entry in result if entry["id"] == str(identifier)), None)


def mutate_disease(db: Session, patient_id: int, data: DiseaseIn | None, identifier: UUID | None = None):
    with clinical_transaction(db) as changes:
        patient = patient_or_404(db, patient_id)
        path, entries, journal = load(db, patient, changes)
        if identifier is None:
            identifier = uuid4()
            entries.append({"id": str(identifier), **data.model_dump()})
        else:
            position = next((i for i, entry in enumerate(entries) if entry["id"] == str(identifier)), None)
            if position is None:
                raise HTTPException(status_code=404, detail="Registro no encontrado para este paciente")
            if data is None:
                entries.pop(position)
            else:
                entries[position] = {"id": str(identifier), **data.model_dump()}
        save(db, patient, path, entries, journal, changes)
        return {"id": str(identifier), "patient_id": patient_id, **data.model_dump()} if data else None
