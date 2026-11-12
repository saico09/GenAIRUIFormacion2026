"""La misma llamada y parámetros para las ramas directa y RAG."""

import os
from time import perf_counter

from app.knowledge import OLLAMA_BASE_URL, request_json
from app.observability import log_event

CHAT_MODEL = os.getenv("CHAT_MODEL", "qwen3.5:4b-q4_K_M")
TEMPERATURE = 0.2
MODEL_OPTIONS = {"temperature": TEMPERATURE, "num_ctx": 8192, "num_predict": 1024,
                 "top_p": 0.95, "top_k": 64, "draft_num_predict": 0}
# Evita cargar el modelo auxiliar especulativo, que falló al iniciar CUDA en este equipo.
THINK = False
TIMEOUT_SECONDS = 180


class LLMUnavailable(Exception):
    """No se pudo obtener una respuesta válida del modelo local."""


def llamar_llm(prompt: str, *, branch: str = "direct", schema: dict | None = None, system: str | None = None) -> str:
    start = perf_counter()
    body = {
        "model": CHAT_MODEL,
        "prompt": prompt,
        "stream": False,
        "think": THINK,
        "options": dict(MODEL_OPTIONS),
        "keep_alive": "1m",
    }
    if schema is not None:
        body["format"] = schema
    if system is not None:
        body["system"] = system
    diagnostics = {
        "model_options": dict(body["options"]),
        "prompt_eval_count": None,
        "prompt_eval_cached_count": None,
        "eval_count": None,
        "ollama_total_duration_ms": None,
        "ollama_load_duration_ms": None,
        "ollama_prompt_eval_duration_ms": None,
        "ollama_eval_duration_ms": None,
        "done_reason": None,
        "thinking_returned": False,
    }
    if "think" in body:
        diagnostics["think_requested"] = body["think"]
    try:
        result = request_json("POST", f"{OLLAMA_BASE_URL}/api/generate", body, timeout=TIMEOUT_SECONDS)
        if not isinstance(result, dict):
            raise ValueError("Respuesta inválida del modelo")
        # Sólo se registra la presencia de thinking, nunca su contenido ni el resultado completo.
        diagnostics["thinking_returned"] = bool(result.get("thinking"))
        diagnostics["done_reason"] = result.get("done_reason")
        for name in ("prompt_eval_count", "prompt_eval_cached_count", "eval_count"):
            count = result.get(name)
            diagnostics[name] = count if type(count) is int and count >= 0 else None
        # Ollama expresa estos tiempos en nanosegundos; el log usa milisegundos.
        # Si el servidor no los entrega, conservar null en vez de inventar ceros.
        for name in ("total_duration", "load_duration", "prompt_eval_duration", "eval_duration"):
            duration = result.get(name)
            if type(duration) is int and duration >= 0:
                diagnostics[f"ollama_{name}_ms"] = round(duration / 1_000_000, 3)
        answer = result["response"]
        if (not isinstance(answer, str) or not answer.strip() or not result.get("done")
                or result.get("done_reason") == "length"):
            raise ValueError("Respuesta incompleta del modelo")
        answer = answer.strip()
    except (OSError, ValueError, KeyError) as error:
        log_event("llm", branch=branch, model=CHAT_MODEL, prompt=prompt, system=system, response=None,
                  duration_ms=round((perf_counter() - start) * 1000, 3), status="error", **diagnostics)
        raise LLMUnavailable("LLM no disponible") from error
    log_event("llm", branch=branch, model=CHAT_MODEL, prompt=prompt, system=system, response=answer,
              duration_ms=round((perf_counter() - start) * 1000, 3), status="ok", **diagnostics)
    return answer
