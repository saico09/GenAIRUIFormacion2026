"""Formato compartido de orientación: el modelo propone, el servidor valida y presenta."""
import logging
import re
import unicodedata

LOGGER = logging.getLogger(__name__)

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
HYPOTHETICAL = re.compile(r"\b(?:hubiera|hubiese|podría|podria|pudiera|vomitar[ií]a|sangrar[ií]a|desmayar[ií]a)\b")
# «no sé si es grave» pregunta, no condiciona lo que se relata después.
INDIRECT_SI = re.compile(r"\b(?:s[eé]|sabe\w*|sabr\w*|pregunt\w*|dud\w*|segur[oa]s? de|dime|averigu\w*)\s+si\b")
# «y» abre otra cláusula sólo ante un verbo explícito, con sujeto/pronombre opcional.
# «no tiene fiebre y dolor» sigue siendo una lista negada.
AFFIRMATIVE_AND = (
    r"\by\s+(?=(?:(?:yo|[eé]l|ella|(?:el|la)\s+paciente)\s+)?"
    r"(?:(?:me|te|se|le|les|nos)\s+)?"
    r"(?:tengo|tiene|siento|siente|estoy|est[aá]|hay|vomito|vomita|sangro|sangra|"
    r"presento|presenta|refiere|duelen?|falta|cuesta|ahogo|ahoga|he|ha)\b)")
CLAUSE_BREAK = (
    r"[.!?;\n]|\bpero\b|,\s*(?=(?:no|ni|sin|(?:me|te|se|le|les|nos)\s+\w+|"
    r"tengo|tiene|siento|siente|estoy|est[aá]|hay|ahora|s[oó]lo\s+que|sino\s+que|aunque)\b)")


def _normalized(text: str) -> str:
    text = unicodedata.normalize("NFC", text.casefold()).strip()
    # «como si no pudiera respirar» compara una sensación presente; no es una condición ni una negación.
    return re.sub(r"\bcomo si(?:\s+no)?\s+\w+", "como", text)


def _clause_prefix(question: str, quote_start: int) -> str:
    prefix = question[:quote_start]
    # Se busca en el relato completo para reconocer el verbo aunque esté dentro de la cita.
    for boundary in re.finditer(CLAUSE_BREAK + "|" + AFFIRMATIVE_AND, question, flags=re.I):
        if boundary.end() > quote_start:
            break
        prefix = question[boundary.end():quote_start]
    return prefix


def _affirmative_quote(question: str, quote: str, quote_start: int | None = None) -> bool:
    quote_start = question.index(quote) if quote_start is None else quote_start
    before = question[:quote_start]
    # La negación alcanza su cláusula; una condición («qué hago si…») alcanza toda la frase.
    clause = _normalized(_clause_prefix(question, quote_start) + quote)
    sentence = INDIRECT_SI.sub(" ", _normalized(re.split(r"[.!?;\n¿]", before)[-1] + quote))
    plain = "".join(c for c in unicodedata.normalize("NFD", clause) if not unicodedata.combining(c))
    if not re.sub(r"\b(?:no|s[ií])\b|\W", "", clause):
        return False
    return not (NEGATION.search(plain) or HYPOTHETICAL.search(clause) or CONDITIONAL_SI.search(sentence))


def _plain(text: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", text.casefold()) if not unicodedata.combining(c))


HISTORICAL = re.compile(
    r"\b(?:historial|antecedentes?|nota anterior|"
    r"en (?:19|20)\d{2}|cuando era|antes(?!\s+de\b)|ya (?:paso|cedio|se resolvio))\b")
REMOTE_TIME = re.compile(r"\bhace (?:\w+ )?(?:anos|meses)\b")
PAST_EVENT = re.compile(r"\b(?:tuve|tenia|presentaba|sufri|vomitaba|dolia|desmaye|no podia)\b")
RESOLVED = re.compile(r"\bya (?:paso|cedio|se resolvio|no (?:me ocurre|me pasa|lo tengo)|no(?=\s*[.!?;]|$))\b")
FUTURE_ONLY = re.compile(r"\b(?:voy|va|vamos|van) a (?:vomitar|sangrar|desmayar\w*)\b")
UNCERTAIN_PRESENCE = re.compile(
    r"\b(?:no (?:se|sabe|tengo claro|estoy segur[oa](?: de)?)|desconozco)\s+si\b")


def _current_quote(question: str, quote: str) -> bool:
    # Una cita puede repetirse: una mención negada anterior no invalida una afirmación posterior.
    for match in re.finditer(re.escape(quote), question):
        before = _clause_prefix(question, match.start())
        after = re.split(CLAUSE_BREAK, question[match.end():], flags=re.I)[0]
        sentence_tail = re.split(r"[.!?;\n]", question[match.end():])[0]
        scope = _plain(before + quote + after)
        # «Me duele desde hace meses» es duración actual; el tiempo remoto solo no prueba un episodio pasado.
        past_episode = REMOTE_TIME.search(scope) and PAST_EVENT.search(scope)
        if (not HISTORICAL.search(scope) and not past_episode
                and not UNCERTAIN_PRESENCE.search(_plain(before + quote))
                and not RESOLVED.search(_plain(quote + sentence_tail))
                and not FUTURE_ONLY.search(_plain(before + quote))
                and _affirmative_quote(question, quote, match.start())):
            return True
    return False


# Equivalencias acotadas para no pedir otra vez un síntoma ya mencionado (también si fue negado).
# No diagnostican enfermedades ni intentan cubrir el vocabulario clínico completo.
SYMPTOM_EQUIVALENTS = tuple(re.compile(pattern) for pattern in (
    r"\b(?:disnea|dificultad (?:de |para |al )?respira\w*|dificultad respiratoria|falta (?:de |el )?aire|cuesta respirar)\b",
    r"\b(?:sibilancias?|wheezing|respiracion sibilante|silbidos?(?: bronquial(?:es)?)?|pitidos?|pitos? (?:en el pecho|al respirar))\b",
    r"\b(?:garganta (?:\w+ ){0,4}(?:tapada|cerrada|cerrando)|cierre de (?:la )?garganta)\b",
    r"\b(?:dolor (?:en (?:el )?|de )?(?:pecho|torax)|dolor toracico|duele (?:el )?pecho)\b",
    r"\b(?:dolor (?:de |en (?:el )?)?(?:estomago|abdomen|barriga)|dolor abdominal|duele (?:el |la )?(?:estomago|barriga))\b",
    r"\b(?:fiebre|febril|temperatura (?:alta|elevada))\b", r"\b(?:hinchazon|hinchad\w*|distension abdominal)\b",
    r"\b(?:reflujo\w*|acidez|agruras?|ardor (?:de |en (?:el )?)?estomago)\b",
    r"\b(?:vomit\w*|emesis)\b", r"\b(?:nauseas?|ganas de vomitar)\b",
    r"\b(?:postura|posicion|de pie|acostarse|acostad[oa]|al acostar\w*)\b",
))


def _new_condition(condition: str, question: str) -> bool:
    condition, question = _plain(condition), _plain(question)
    if any(pattern.search(condition) and pattern.search(question) for pattern in SYMPTOM_EQUIVALENTS):
        return False
    # Cotejo léxico: tolera tildes, puntuación y artículos, sin equiparar palabras sólo por prefijo.
    stopwords = {"de", "del", "la", "el", "los", "las", "en", "al", "un", "una", "y", "o", "con", "sin",
                 "nuevo", "nueva", "nuevos", "nuevas", "persistente", "persistentes", "intenso", "intensa"}
    words = lambda text: {word for word in re.findall(r"\w+", text) if word not in stopwords}
    added, reported = words(condition), words(question)
    return bool(added) and not added.issubset(reported)


def _new_detail(detail: str, question: str) -> bool:
    # «Desde ayer» ya sitúa el inicio; no exigir más precisión para poder orientar.
    timing_given = re.search(
        r"\b(?:desde (?:ayer|anoche|hoy)|hace (?:\w+ ){1,3}(?:horas?|dias?|semanas?|meses|anos))\b",
        _plain(question))
    asks_timing = re.search(r"\b(?:duracion|inicio|desde cuando|cuando (?:empezo|comenzo))\b", _plain(detail))
    return not (timing_given and asks_timing) and _new_condition(detail, question)


EXPLICIT_ALERT = re.compile(
    r"\b(?:no (?:puedo|puede|logro|logra) respirar|sin poder respirar|no (?:estoy|esta) respirando(?: bien)?|"
    r"(?:vomito|vomita|vomitas|vomitan|vomitando|vomite|vomitado)(?:\s+\w+){0,2}\s+sangre|sangre (?:en (?:el |las )?)?(?:vomito|heces)|"
    r"dolor (?:en (?:el )?|de )?(?:pecho|torax)|dolor toracico|(?:me |le )?duele (?:el )?pecho|"
    r"(?:me |se )?desmay\w*|(?:perdi|perdio) (?:el )?conocimiento|"
    r"dolor intenso(?:\s+\w+){0,5}\s+no (?:cede|se calma))\b")
THROAT_CLOSING = re.compile(r"\bgarganta\b.{0,45}\b(?:tapada|cerrada|cerrando)\b|\bcierre de (?:la )?garganta\b")


def explicit_current_alert(question: str) -> str | None:
    """Conserva una acción urgente ante señales explícitas; nunca elige un diagnóstico."""
    # El mapa conserva citas literales incluso si una tilde ocupa dos caracteres Unicode.
    characters, positions = [], []
    for index, character in enumerate(question):
        for folded in _plain(character):
            characters.append(folded)
            positions.append(index)
    plain = "".join(characters)

    def original(start, end):
        finish = positions[end - 1] + 1
        while finish < len(question) and unicodedata.combining(question[finish]):
            finish += 1
        return question[positions[start]:finish]

    for match in EXPLICIT_ALERT.finditer(plain):
        quote = original(match.start(), match.end())
        if _current_quote(question, quote):
            return quote
    # La combinación del caso de Marco no debe depender de que el modelo marque la alerta.
    breathing = SYMPTOM_EQUIVALENTS[0].search(plain)
    throat = THROAT_CLOSING.search(plain)
    if breathing and throat:
        start, end = min(breathing.start(), throat.start()), max(breathing.end(), throat.end())
        quote = original(start, end)
        if len(quote) <= 240 and _current_quote(question, quote):
            return quote
    return None


TEXT_PATTERN = r"^[^¿?\r\n\[\]_\u0000-\u0020][^¿?\r\n\[\]_\u0000-\u001f]*$"


def _short_fragments(question: str):
    # Se separan listas para citar síntomas concretos; _current_quote conserva su negación original.
    for clause in re.split(r"[,;.!?\n]+|\by\b|\bpero\b", question, flags=re.I):
        start, end = 0, 0
        for word in re.finditer(r"\S+", clause):
            if word.end() - start > 240:
                if end > start:
                    yield clause[start:end]
                start = word.start()
            end = word.end()
        if end > start:
            yield clause[start:end]


def _candidate_quotes(question: str, *, short: bool = False) -> list[str]:
    # Una coma corta sólo ante otra negación o un verbo nuevo: así una negación inicial cubre su lista entera.
    sentences = re.split(r"[.!?;\n]+", question)
    clauses = re.split(r"¿[^?]*\?|\by\s+(?=no\b)|" + CLAUSE_BREAK,
                       question, flags=re.I)
    # Se conserva también la frase completa cuando ambas partes son afirmativas.
    clauses += [part for clause in clauses for part in re.split(AFFIRMATIVE_AND, clause, flags=re.I)]
    fragments = list(_short_fragments(question)) if short else []
    candidates = [candidate.strip(" ,") for candidate in (question, *sentences, *clauses, *fragments)]
    return list(dict.fromkeys(candidate for candidate in candidates
                              if 0 < len(candidate) <= 240 and re.fullmatch(TEXT_PATTERN, candidate)
                              and not re.search(r"\bni\b", candidate, re.I)
                              and _current_quote(question, candidate)))


def orientation_schema(question: str = "") -> dict:
    # Ollama descarta esquemas con pattern; maxLength puede cortar palabras durante la generación.
    text = {"type": "string", "minLength": 1}
    quotes = _candidate_quotes(question, short=True)
    return {"type": "object", "properties": {
        "possibilities": {"type": "array", "minItems": int(bool(quotes)), "maxItems": 3 if quotes else 0, "items": {
            "type": "object", "properties": {"cause": text,
                "evidence": {"type": "array", "minItems": int(bool(quotes)), "maxItems": 3 if quotes else 0,
                             "items": {**text, "enum": quotes} if quotes else text},
                "condition": {"type": ["string", "null"], "minLength": 1}},
            "required": ["cause", "evidence", "condition"], "additionalProperties": False}},
        "optional_details": {"type": "array", "minItems": 0, "maxItems": 2, "items": text},
        "current_alert": {"type": ["string", "null"], "enum": [None, *_candidate_quotes(question)]}},
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


def _render_possibility(possibility: dict, index: int, question: str) -> str:
    if not isinstance(possibility, dict) or set(possibility) != {"cause", "evidence", "condition"}:
        raise ValueError("Posibilidad inválida")
    cause = _phrase(possibility["cause"], 120)
    evidence, condition = possibility["evidence"], possibility["condition"]
    if not isinstance(evidence, list) or len(evidence) > 3:
        raise ValueError("La evidencia requiere hasta tres citas actuales")
    quotes = [_text(quote, 240) for quote in evidence]
    if not quotes:
        raise ValueError("Una posibilidad requiere al menos una cita actual")
    if any(not _current_quote(question, quote) for quote in quotes):
        raise ValueError("La evidencia debe citar síntomas afirmados en el relato actual")
    if index == 0 and condition is not None:
        raise ValueError("La primera posibilidad debe apoyarse en síntomas presentes, sin condición adicional")
    if index > 0 and condition is None:
        raise ValueError("Una alternativa necesita una condición adicional no relatada")
    if condition is not None:
        condition = _phrase(condition, 220)
        if not _new_condition(condition, question):
            raise ValueError("La condición repite un dato ya relatado o negado")
        return f"Podría ser {cause} si además hubiera {condition}."
    if quotes:
        cited = ", ".join(f"«{quote}»" for quote in dict.fromkeys(quotes))
        return f"Por lo que describes ({cited}), la posibilidad principal es {cause}."
    raise ValueError("Una posibilidad requiere evidencia actual o una condición adicional")


def render_orientation(value: dict, question: str, *, background: str = "") -> str:
    if not isinstance(value, dict) or set(value) != {"possibilities", "optional_details", "current_alert"}:
        raise ValueError("Formato de orientación inválido")
    possibilities, details = value["possibilities"], value["optional_details"]
    if not isinstance(possibilities, list) or len(possibilities) > 3:
        raise ValueError("La orientación admite hasta tres posibilidades")
    if not possibilities and _candidate_quotes(question, short=True):
        raise ValueError("Un relato actual afirmado requiere una posibilidad")
    if not isinstance(details, list) or len(details) > 2:
        raise ValueError("Se admiten hasta dos detalles opcionales")
    parts = []
    alert = value["current_alert"]
    if alert is not None:
        alert = _text(alert, 240)
        if alert not in question:
            raise ValueError("La alerta no cita el relato actual")
        # Una cita literal negada o hipotética tampoco acredita una alarma actual.
        if not _current_quote(question, alert):
            raise ValueError("La evidencia de alarma es negativa, condicional o histórica")
    alert = explicit_current_alert(question) or alert
    if alert is not None:
        parts.append(f"Busca atención urgente por lo que relatas: «{alert}».")
    if not possibilities:
        parts.append("No describes síntomas actuales afirmados para proponer una causa.")
    for index, possibility in enumerate(possibilities):
        try:
            parts.append(_render_possibility(possibility, index, question))
        except ValueError as error:
            if index == 0:
                raise
            LOGGER.warning("orientation_filtered field=possibilities index=%s reason=%s", index, error)
    if background:
        parts.append(background)
    # Un detalle escrito como pregunta («¿Desde cuándo?») se muestra como dato, sin abrir un cuestionario.
    details = [re.sub(r"(?:^\s*¿)|(?:\?\s*$)", "", detail) if isinstance(detail, str) else detail for detail in details]
    available = []
    for index, detail in enumerate(details):
        phrase = _phrase(detail, 120)
        if _new_detail(phrase, question):
            available.append(phrase)
        else:
            LOGGER.warning("orientation_filtered field=optional_details index=%s reason=already_reported", index)
    if available:
        parts.append("Para afinar la orientación, puedes añadir: " + "; ".join(available) + ".")
    parts.append(DISCLAIMER)
    return "\n\n".join(parts)
