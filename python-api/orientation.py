"""Formato compartido de orientación: el modelo propone, el servidor valida y presenta."""
import re
import unicodedata


def _affirmative_quote(question: str, quote: str) -> bool:
    # Revisar toda la cita, incluso si termina en puntuación o reúne varias frases.
    # El prefijo conserva una negación que el modelo haya dejado fuera de la cita.
    before = question[:question.index(quote)]
    context = re.split(r"[.!?;,\n]|\bpero\b", before, flags=re.I)[-1] + quote
    normalized = "".join(c for c in unicodedata.normalize("NFD", context.casefold()) if not unicodedata.combining(c))
    return not re.search(r"\b(?:no|sin|niega|niego|si|hubiera|podria)\b", normalized)


def orientation_schema(question: str = "") -> dict:
    def text(limit):
        return {"type": "string", "minLength": 1, "maxLength": limit,
                "pattern": r"^[^¿?\r\n\[\]\u0000-\u0020][^¿?\r\n\[\]\u0000-\u001f]*$"}
    # Se ofrecen frases completas, sin cortar sus negaciones ni inventar citas.
    # Esto limita el formato; decidir si describen una alarma sigue siendo tarea del modelo.
    candidates = [question.strip(), *re.split(r"[.!?;\n]+", question)]
    quotes = list(dict.fromkeys(candidate.strip() for candidate in candidates
                               if 0 < len(candidate.strip()) <= 240
                               and re.fullmatch(text(240)["pattern"], candidate.strip())
                               and _affirmative_quote(question, candidate.strip())))
    return {"type": "object", "properties": {
        "possibilities": {"type": "array", "maxItems": 3, "items": {
            "type": "object", "properties": {
                "cause": text(120), "condition": text(220)},
            "required": ["cause", "condition"], "additionalProperties": False}},
        "optional_details": {"type": "array", "minItems": 2, "maxItems": 3,
                             "items": text(120)},
        "current_alert": {**text(240), "type": ["string", "null"], "enum": [None, *quotes]}},
        "required": ["possibilities", "optional_details", "current_alert"], "additionalProperties": False}


def _text(value, limit):
    if (not isinstance(value, str) or not value.strip() or len(value) > limit
            or any(character in value for character in "¿?\r\n[]")
            or any(ord(character) < 32 for character in value)):
        raise ValueError("La orientación contiene un campo inválido")
    return value.strip()


def render_orientation(value: dict, question: str, *, background: str = "") -> str:
    if not isinstance(value, dict) or set(value) != {"possibilities", "optional_details", "current_alert"}:
        raise ValueError("Formato de orientación inválido")
    possibilities, details = value["possibilities"], value["optional_details"]
    if not isinstance(possibilities, list) or len(possibilities) > 3:
        raise ValueError("La orientación admite hasta tres posibilidades")
    if not isinstance(details, list) or not 2 <= len(details) <= 3:
        raise ValueError("Se requieren dos o tres detalles opcionales")
    parts = []
    alert = value["current_alert"]
    if alert is not None:
        alert = _text(alert, 240)
        if alert not in question:
            raise ValueError("La alerta no cita el relato actual")
        # Una cita literal negada o hipotética tampoco acredita una alarma actual.
        if not _affirmative_quote(question, alert):
            raise ValueError("La evidencia de alarma es negativa o condicional")
        parts.append(f"Busca atención urgente por lo que relatas: «{alert}».")
    for possibility in possibilities:
        if not isinstance(possibility, dict) or set(possibility) != {"cause", "condition"}:
            raise ValueError("Posibilidad inválida")
        cause = _text(possibility["cause"], 120)
        condition = _text(possibility["condition"], 220)
        parts.append(f"Podría ser {cause} si además hubiera {condition}.")
    if not possibilities and alert is None:
        parts.append("El malestar descrito no permite priorizar una causa concreta.")
    if background:
        parts.append(background)
    parts.append("Para afinar la orientación, puedes añadir: " + "; ".join(_text(detail, 120) for detail in details) + ".")
    parts.append("Hipótesis sin confirmar; requiere evaluación clínica para confirmarla.")
    return "\n\n".join(parts)
