"""Formato compartido de orientación: el modelo propone, el servidor valida y presenta."""
import re
import unicodedata

DISCLAIMER = "Respuesta generada por un chatbot de IA; puede cometer errores. Para mayor certeza, consulta con un médico."
# Sólo niega la frase que niega la presencia del síntoma («no tiene», «no siente», «niega», «sin» al inicio…).
# «no puede respirar» o «dolor que no se calma» describen un síntoma presente.
NEGATION = re.compile(
    r"\b(?:niega|niego|nego)\b|(?:^|[.,;:]\s*)(?:sin|ni)\s+(?!poder\b|lograr\b|conseguir\b|siquiera\b|embargo\b)"
    r"|\b(?:no|nunca|tampoco)\s+(?:(?:me|le|les|se|lo|la)\s+)?(?:"
    r"tien\w*|teng\w*|tuv\w*|sient\w*|sint\w*|present\w*|refier\w*|hay|hubo|(?:esta\w*|estoy|estuv\w*)(?!\s+respir)|"
    r"vomit\w*|sangr\w*|duel\w*|not[ao]\w*|sufr\w*|padec\w*|muestr\w*|desmay\w*|falt\w*|cuest\w*|"
    r"perdi\w*|pierd\w*|(?:vi|veo|vio)\s+sangre|"
    r"(?:ha|he|han|habia)\s+(?:tenido|sentido|presentado|referido|notado|vomitado|sangrado|sufrido|"
    r"desmayado|perdido|visto))\b")
# «si» sin tilde abre una condición; «sí», «Si, tiene…» o «creo que si» no la abren.
CONDITIONAL_SI = re.compile(r"\bsi\b(?!\s*(?:[,.;:!]|$))")
HYPOTHETICAL = re.compile(r"\b(?:hubiera|hubiese|podría|podria|pudiera)\b")
# «no sé si es grave» pregunta, no condiciona lo que se relata después.
INDIRECT_SI = re.compile(r"\b(?:s[eé]|sabe\w*|sabr\w*|pregunt\w*|dud\w*|segur[oa]s? de|dime|averigu\w*)\s+si\b")
# «y» abre otra cláusula sólo ante un verbo explícito, con sujeto/pronombre opcional.
# «no tiene fiebre y dolor» sigue siendo una lista negada.
AFFIRMATIVE_AND = (
    r"\by\s+(?=(?:(?:yo|[eé]l|ella|(?:el|la)\s+paciente)\s+)?"
    r"(?:(?:me|te|se|le|les|nos)\s+)?"
    r"(?:tengo|tiene|siento|siente|estoy|est[aá]|hay|vomito|vomita|sangro|sangra|"
    r"presento|presenta|refiere|duelen?|falta|cuesta|ahogo|ahoga|he|ha)\b)")


def _normalized(text: str) -> str:
    text = unicodedata.normalize("NFC", text.casefold()).strip()
    # «como si no pudiera respirar» compara una sensación presente; no es una condición ni una negación.
    return re.sub(r"\bcomo si(?:\s+no)?\s+\w+", "como", text)


def _affirmative_quote(question: str, quote: str) -> bool:
    quote_start = question.index(quote)
    before = question[:quote_start]
    clause_before = before
    # Se busca en el relato completo para reconocer el verbo aunque esté dentro de la cita.
    for boundary in re.finditer(AFFIRMATIVE_AND, question, flags=re.I):
        if boundary.end() > quote_start:
            break
        clause_before = question[boundary.end():quote_start]
    # La negación alcanza su cláusula; una condición («qué hago si…») alcanza toda la frase.
    clause = _normalized(re.split(r"[.!?;,\n]|\bpero\b", clause_before, flags=re.I)[-1] + quote)
    sentence = INDIRECT_SI.sub(" ", _normalized(re.split(r"[.!?;\n¿]", before)[-1] + quote))
    plain = "".join(c for c in unicodedata.normalize("NFD", clause) if not unicodedata.combining(c))
    if not re.sub(r"\b(?:no|s[ií])\b|\W", "", clause):
        return False
    return not (NEGATION.search(plain) or HYPOTHETICAL.search(clause) or CONDITIONAL_SI.search(sentence))


TEXT_PATTERN = r"^[^¿?\r\n\[\]_\u0000-\u0020][^¿?\r\n\[\]_\u0000-\u001f]*$"


def orientation_schema(question: str = "") -> dict:
    # El esquema fija sólo la estructura y _text valida después: Ollama 0.40 descarta el esquema
    # entero si un texto lleva "pattern", y "maxLength" corta palabras.
    text = {"type": "string", "minLength": 1}
    # Una coma corta sólo ante otra negación o un verbo nuevo: así una negación inicial cubre su lista entera.
    sentences = re.split(r"[.!?;\n]+", question)
    clauses = re.split(r"¿[^?]*\?|[.!?;\n]+|\bpero\b|\by\s+(?=no\b)|,\s*(?=(?:no|ni|sin|(?:me|te|se|le|les|nos)\s+\w+|"
                       r"tengo|tiene|siento|siente|estoy|est[aá]|hay|ahora|s[oó]lo\s+que|sino\s+que|aunque)\b)",
                       question, flags=re.I)
    # Se conserva también la frase completa cuando ambas partes son afirmativas.
    clauses += [part for clause in clauses for part in re.split(AFFIRMATIVE_AND, clause, flags=re.I)]
    candidates = [candidate.strip(" ,") for candidate in (question, *sentences, *clauses)]
    quotes = list(dict.fromkeys(candidate for candidate in candidates
                               if 0 < len(candidate) <= 240 and re.fullmatch(TEXT_PATTERN, candidate)
                               and not re.search(r"\bni\b", candidate, re.I)
                               and _affirmative_quote(question, candidate)))
    return {"type": "object", "properties": {
        "possibilities": {"type": "array", "minItems": 1, "maxItems": 3, "items": {
            "type": "object", "properties": {"cause": text, "condition": text},
            "required": ["cause", "condition"], "additionalProperties": False}},
        "optional_details": {"type": "array", "minItems": 2, "maxItems": 3, "items": text},
        "current_alert": {"type": ["string", "null"], "enum": [None, *quotes]}},
        "required": ["possibilities", "optional_details", "current_alert"], "additionalProperties": False}


def _text(value, limit):
    # «_» delata identificadores tipo variable («frecuencia_dia»).
    if (not isinstance(value, str) or not value.strip() or len(value) > limit
            or any(character in value for character in "¿?\r\n[]_")
            or any(ord(character) < 32 for character in value)):
        raise ValueError("La orientación contiene un campo inválido")
    return value.strip()


def _phrase(value, limit):
    """Texto para insertar a mitad de frase: sin punto final y en minúscula, salvo siglas (ERGE)."""
    value = _text(value, limit).rstrip(" .…")
    if not value:
        raise ValueError("La orientación contiene un campo inválido")
    words = value.split(" ")
    # Si toda la frase viene en mayúscula inicial («Higiene Oral Insuficiente»), se aplica a cada palabra.
    title_case = len(words) > 1 and all(word[:1].isupper() for word in words if word[:1].isalpha())
    for index, word in enumerate(words if title_case else words[:1]):
        # Una inicial abreviada («H. pylori») también se respeta.
        if (word[:1].isalpha() and not word.endswith(".")
                and not any(character.isupper() for character in word[1:])):
            words[index] = word[0].lower() + word[1:]
    return " ".join(words)


def render_orientation(value: dict, question: str, *, background: str = "") -> str:
    if not isinstance(value, dict) or set(value) != {"possibilities", "optional_details", "current_alert"}:
        raise ValueError("Formato de orientación inválido")
    possibilities, details = value["possibilities"], value["optional_details"]
    if not isinstance(possibilities, list) or not 1 <= len(possibilities) <= 3:
        raise ValueError("La orientación requiere entre una y tres posibilidades")
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
        cause = _phrase(possibility["cause"], 120)
        condition = _phrase(possibility["condition"], 220)
        parts.append(f"Podría ser {cause} si además hubiera {condition}.")
    if background:
        parts.append(background)
    # Un detalle escrito como pregunta («¿Desde cuándo?») se muestra como dato, sin abrir un cuestionario.
    details = [re.sub(r"(?:^\s*¿)|(?:\?\s*$)", "", detail) if isinstance(detail, str) else detail for detail in details]
    parts.append("Para afinar la orientación, puedes añadir: " + "; ".join(_phrase(detail, 120) for detail in details) + ".")
    parts.append(DISCLAIMER)
    return "\n\n".join(parts)
