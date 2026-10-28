"""La misma llamada y parámetros para las ramas directa y RAG."""

import os
from time import perf_counter

from app.knowledge import OLLAMA_BASE_URL, request_json
from app.observability import log_event

CHAT_MODEL = os.getenv("CHAT_MODEL", "llama3.2:3b")
TEMPERATURE = 0
TIMEOUT_SECONDS = 120


class LLMUnavailable(Exception):
    """No se pudo obtener una respuesta válida del modelo local."""


def llamar_llm(prompt: str, *, branch: str = "direct") -> str:
    start = perf_counter()
    try:
        result = request_json("POST", f"{OLLAMA_BASE_URL}/api/generate", {
            "model": CHAT_MODEL,
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": TEMPERATURE, "num_ctx": 2048, "num_predict": 256},
            "keep_alive": "1m",
        }, timeout=TIMEOUT_SECONDS)
        answer = result["response"]
        if not isinstance(answer, str) or not answer.strip() or not result.get("done"):
            raise ValueError("Respuesta incompleta del modelo")
        answer = answer.strip()
    except (OSError, ValueError, KeyError) as error:
        log_event("llm", branch=branch, model=CHAT_MODEL, prompt=prompt, response=None,
                  duration_ms=round((perf_counter() - start) * 1000, 3), status="error")
        raise LLMUnavailable("LLM no disponible") from error
    log_event("llm", branch=branch, model=CHAT_MODEL, prompt=prompt, response=answer,
              duration_ms=round((perf_counter() - start) * 1000, 3), status="ok")
    return answer
