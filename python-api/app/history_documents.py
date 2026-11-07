"""Formato de historias de práctica: tres campos asociados por un UUID estable."""

import hashlib
from pathlib import Path
import re
from uuid import NAMESPACE_URL, UUID, uuid5

SECTIONS = {"Enfermedad": "disease", "Tratamiento": "treatment", "Medicamento": "medication"}
UNRECORDED = "No registrado."


def parse_history(markdown: str, filename: str) -> dict:
    """Parser para la ingesta por consola; Java valida las ediciones de la interfaz."""
    if len(markdown.encode("utf-8")) > 1048576:
        raise ValueError("El informe supera 1 MiB")
    normalized = markdown.replace("\r\n", "\n")
    clinical, _, journal = normalized.partition("\n## Consultas registradas\n")
    parts = re.split(r"^## Registro (.+)$", clinical, flags=re.M)
    ids = re.findall(r"^patient_id: ([1-9][0-9]*)$", parts[0], re.M)
    if len(ids) != 1:
        raise ValueError(f"{filename}: se requiere un único patient_id positivo")
    patient_id = int(ids[0])
    if not re.fullmatch(rf"paciente-{patient_id}-[a-z0-9-]+\.md", filename):
        raise ValueError("Nombre de informe distinto de su paciente")
    if not re.fullmatch(r"# Historia clínica ficticia — [^\n]+\n\nDatos ficticios para la formación\.\n\npatient_id: "
                        + str(patient_id) + r"\n\s*", parts[0]):
        raise ValueError("Encabezado de historia inválido")
    entries = []
    seen = set()
    for identifier, body in zip(parts[1::2], parts[2::2], strict=True):
        if str(UUID(identifier)) != identifier:
            raise ValueError("El ID de registro debe ser un UUID canónico")
        if identifier in seen:
            raise ValueError("ID de registro duplicado")
        seen.add(identifier)
        sections = re.split(r"^### (.+)$", body, flags=re.M)
        if sections[0].strip() or sections[1::2] != list(SECTIONS):
            raise ValueError("Cada registro necesita Enfermedad, Tratamiento y Medicamento, en ese orden")
        entry = {"id": identifier}
        for section, value in zip(sections[1::2], sections[2::2], strict=True):
            value = value.strip()
            if not value or len(value) > 2000 or re.search(r"^#{1,6}(?:\s|$)", value, re.M):
                raise ValueError(f"Campo {section} inválido")
            entry[SECTIONS[section]] = "" if value == UNRECORDED else value
        if not any(entry[key] for key in SECTIONS.values()):
            raise ValueError("Un registro necesita al menos un dato explícito")
        entries.append(entry)
    if len(entries) > 50:
        raise ValueError("Máximo 50 registros por informe")
    consultations = []
    # El journal automático contiene texto citado: sólo se ingiere la nota del usuario.
    # Las respuestas de IA nunca vuelven al índice como si fueran evidencia clínica.
    if journal:
        for match in re.finditer(r"^### Consulta ([0-9a-f-]{36})\n\nFecha UTC: ([^\n]+)\n\nModelo: [^\n]+\n\n"
                                 r"#### Nota reportada\n(.*?)\n\n#### Respuesta sin RAG\n", journal, re.M | re.S):
            identifier, created, quoted = match.groups()
            if str(UUID(identifier)) != identifier or any(not line.startswith("> ") for line in quoted.split("\n")):
                raise ValueError("Consulta automática inválida")
            consultations.append({"id": identifier, "created_at": created,
                                  "question": "\n".join(line[2:] for line in quoted.split("\n"))})
        if len(consultations) != len(re.findall(r"^### Consulta ", journal, re.M)):
            raise ValueError("No se pudieron leer todas las consultas automáticas")
    return {"patient_id": patient_id, "filename": filename, "markdown": markdown,
            "revision": hashlib.sha256(markdown.encode("utf-8")).hexdigest(), "entries": entries,
            "consultations": consultations}


def fragments_from_history(history: dict) -> list[dict]:
    patient_id = history["patient_id"]
    fragments = []
    for entry in history["entries"]:
        for section, field in SECTIONS.items():
            identifier = str(uuid5(NAMESPACE_URL, f"genai:java:historia:{patient_id}:{entry['id']}:{section}"))
            fragments.append({"id": identifier, "payload": {
                "patient_id": patient_id, "registry": "java", "record_id": entry["id"],
                "kind": "confirmed_record",
                "source": history["filename"], "section": section,
                "text": entry[field] or UNRECORDED, "revision": history["revision"],
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
