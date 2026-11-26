"""Formato de historias de práctica: tres campos asociados por un UUID estable.

Mismas reglas que HistoryMarkdown.java: un cambio de formato aquí debe repetirse allá.
"""

import hashlib
from pathlib import Path
import re
from uuid import NAMESPACE_URL, UUID, uuid5

from app.schemas import EMPTY, clinical

SECTIONS = {"Enfermedad": "disease", "Tratamiento": "treatment", "Medicamento": "medication"}
UNRECORDED = EMPTY
MAX_BYTES = 1048576
MAX_ENTRIES = 50
SIZE_MESSAGE = "El Markdown admite como máximo 1 MiB UTF-8"
JOURNAL_HEADING = "\n## Consultas registradas\n"
ENTRY_HEADING = "\n## Registro "
DISEASE_HEADING = "\n\n### Enfermedad\n"
TREATMENT_HEADING = "\n\n### Tratamiento\n"
MEDICATION_HEADING = "\n\n### Medicamento\n"
SECTIONS_MESSAGE = "Usa Registro, Enfermedad, Tratamiento y Medicamento con sus encabezados originales"
UUID_PATTERN = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")
# La ingesta por consola no conoce al paciente: toma nombre e ID de la propia cabecera.
HEADER = re.compile(r"# Historia clínica ficticia — [^\n]+\n\nDatos ficticios para la formación\.\n\n"
                    r"patient_id: ([1-9][0-9]*)\n")


def check_size(markdown: str):
    if len(markdown.encode("utf-8")) > MAX_BYTES:
        raise ValueError(SIZE_MESSAGE)


def skip_blank_lines(body: str) -> str:
    start = 0
    while start < len(body):
        end = body.find("\n", start)
        end = len(body) if end < 0 else end
        if body[start:end].strip(" \t"):
            return "\n" + body[start:]
        start = end + 1
    return ""


def comparable_journal(text: str) -> str:
    """Un editor puede quitar los espacios o el salto finales; se compara sin ellos y se guarda el formato original."""
    lines = text.replace("\r\n", "\n").split("\n")
    return "\n".join(line.rstrip(" \t") for line in lines).rstrip("\n")


def check_history(markdown: str, header: str, journal: str | None) -> tuple[list[dict], str]:
    """Mismas reglas que HistoryMarkdown.parse; journal=None (ingesta por consola) no compara el diario con SQL."""
    check_size(markdown)
    normalized = markdown.replace("\r\n", "\n")
    if not normalized.startswith(header):
        raise ValueError("El título y patient_id deben conservar el propietario del informe")
    body, separator, actual = skip_blank_lines(normalized[len(header):]).partition(JOURNAL_HEADING)
    if journal is not None and separator:
        if comparable_journal(separator + actual) != comparable_journal(journal):
            raise ValueError("Las consultas automáticas son históricas; edita sólo los registros "
                             "confirmados antes de Consultas registradas")
    elif journal:
        raise ValueError("Conserva la sección Consultas registradas sin cambios")
    return parse_entries(body), actual


def parse_entries(body: str) -> list[dict]:
    # Los separadores se recorren una vez: un informe mal formado no provoca backtracking.
    entries, seen, offset = [], set(), 0
    while offset < len(body):
        if len(entries) == MAX_ENTRIES:
            raise ValueError("La historia admite como máximo 50 registros")
        if not body.startswith(ENTRY_HEADING, offset):
            raise ValueError("Estructura Markdown inválida")
        id_start = offset + len(ENTRY_HEADING)
        id_end = id_start + 36
        if id_end > len(body) or not body.startswith(DISEASE_HEADING, id_end):
            raise ValueError(SECTIONS_MESSAGE)
        identifier = body[id_start:id_end]
        if not UUID_PATTERN.fullmatch(identifier) or identifier in seen:
            raise ValueError("Cada registro requiere un UUID válido y único")
        seen.add(identifier)
        disease = id_end + len(DISEASE_HEADING)
        next_entry = body.find(ENTRY_HEADING, disease)
        end = len(body) if next_entry < 0 else next_entry
        treatment = section_offset(body, TREATMENT_HEADING, disease, end)
        medication = section_offset(body, MEDICATION_HEADING, treatment + len(TREATMENT_HEADING), end)
        entries.append(entry(identifier, body[disease:treatment],
                             body[treatment + len(TREATMENT_HEADING):medication],
                             body[medication + len(MEDICATION_HEADING):end]))
        offset = end
    return entries


def section_offset(body: str, heading: str, start: int, end: int) -> int:
    offset = body.find(heading, start)
    if offset < 0 or offset + len(heading) > end:
        raise ValueError(SECTIONS_MESSAGE)
    return offset


def entry(identifier: str, *values: str) -> dict:
    result = {"id": identifier}
    for (section, field), value in zip(SECTIONS.items(), values, strict=True):
        try:
            result[field] = clinical(value)
        except ValueError as error:
            raise ValueError(f"{section}: {error}") from None
    if not any(result[field] for field in SECTIONS.values()):
        raise ValueError("Un registro necesita al menos un campo con información")
    return result


def parse_history(markdown: str, filename: str) -> dict:
    """Parser para la ingesta por consola; mismas reglas que Java salvo comparar el diario con SQL."""
    check_size(markdown)
    header = HEADER.match(markdown.replace("\r\n", "\n"))
    if header is None:
        raise ValueError("Encabezado de historia inválido")
    patient_id = int(header[1])
    if not re.fullmatch(rf"paciente-{patient_id}-[a-z0-9-]+\.md", filename):
        raise ValueError("Nombre de informe distinto de su paciente")
    entries, journal = check_history(markdown, header[0], None)
    consultations = []
    # El journal automático contiene texto citado: sólo se ingiere la nota del usuario.
    # Las respuestas de IA nunca vuelven al índice como si fueran evidencia clínica.
    if journal:
        for match in re.finditer(r"^### Consulta ([0-9a-f-]{36})\n\nFecha UTC: ([^\n]+)\n\nModelo: [^\n]+\n\n"
                                 r"#### Nota reportada\n(.*?)\n\n#### Respuesta sin RAG\n", journal, re.M | re.S):
            identifier, created, quoted = match.groups()
            lines = quoted.split("\n")
            # Una línea "> " vacía puede quedar como ">" si el editor quitó el espacio final.
            if str(UUID(identifier)) != identifier or any(line != ">" and not line.startswith("> ") for line in lines):
                raise ValueError("Consulta automática inválida")
            consultations.append({"id": identifier, "created_at": created,
                                  "question": "\n".join(line[2:] for line in lines)})
        if len(consultations) != len(re.findall(r"^### Consulta ", journal, re.M)):
            raise ValueError("No se pudieron leer todas las consultas automáticas")
    return {"patient_id": patient_id, "filename": filename, "markdown": markdown,
            "revision": hashlib.sha256(markdown.encode("utf-8")).hexdigest(), "entries": entries,
            "consultations": consultations}


def fragments_from_history(history: dict) -> list[dict]:
    patient_id = history["patient_id"]
    fragments = []
    for entry_data in history["entries"]:
        for section, field in SECTIONS.items():
            identifier = str(uuid5(NAMESPACE_URL, f"genai:java:historia:{patient_id}:{entry_data['id']}:{section}"))
            fragments.append({"id": identifier, "payload": {
                "patient_id": patient_id, "registry": "java", "record_id": entry_data["id"],
                "kind": "confirmed_record",
                "source": history["filename"], "section": section,
                "text": entry_data[field] or UNRECORDED, "revision": history["revision"],
            }})
    for consultation in history.get("consultations", []):
        identifier = str(uuid5(NAMESPACE_URL, f"genai:java:consulta:{patient_id}:{consultation['id']}"))
        fragments.append({"id": identifier, "payload": {
            "patient_id": patient_id, "registry": "java", "record_id": consultation["id"],
            "kind": "reported_consultation", "source": history["filename"], "section": "Consulta",
            "text": f"Consulta registrada el {consultation['created_at']}. Texto relatado o preguntado por el usuario, sin diagnóstico confirmado:\n{consultation['question']}",
            "revision": history["revision"],
        }})
    return fragments


def load_histories(data_dir: Path) -> list[dict]:
    paths = sorted(data_dir.glob("paciente-*.md"))
    if not paths:
        raise ValueError(f"No hay historias en {data_dir}")
    histories = []
    for path in paths:
        # La revisión identifica los bytes del archivo, igual que Files.readString en Java.
        # read_text normaliza CRLF en Windows y produciría una revisión distinta.
        with path.open(encoding="utf-8", newline="") as stream:
            histories.append(parse_history(stream.read(), path.name))
    if len({history["patient_id"] for history in histories}) != len(histories):
        raise ValueError("Hay más de un informe para el mismo paciente")
    return histories
