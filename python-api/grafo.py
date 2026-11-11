"""RAG en cuatro pasos reutilizado por el chatbot y por la ejecución desde consola."""

import json
from typing import NotRequired, TypedDict

from langgraph.graph import END, START, StateGraph

from app.knowledge import search_fragments
from app.llm import CHAT_MODEL, MODEL_OPTIONS, THINK, llamar_llm
from app.observability import log_event, request_id_context
from app.tracing import trace_node
from rag import RAG_SYSTEM, build_rag_prompt, rag_response_schema, validate_rag_answer


class EstadoRag(TypedDict):
    pregunta: str
    patient_id: int
    request_id: str
    patient_name: NotRequired[str]
    fragmentos: NotRequired[list[dict]]
    prompt: NotRequired[str]
    respuesta: NotRequired[str]


@trace_node("patient_id", "pregunta", kind="RETRIEVER")
def retrieval(state: EstadoRag) -> dict:
    log_event("rag_node", node="retrieval", request_id=state["request_id"])
    return {"fragmentos": search_fragments(state["patient_id"], state["pregunta"])}


@trace_node("pregunta", "fragmentos")
def prompt(state: EstadoRag) -> dict:
    log_event("rag_node", node="prompt", request_id=state["request_id"])
    return {"prompt": build_rag_prompt(state["pregunta"], state["fragmentos"], state.get("patient_name"))}


@trace_node("prompt", kind="LLM", attributes={
    "llm.model_name": CHAT_MODEL,
    "llm.invocation_parameters": json.dumps({**MODEL_OPTIONS, "think": THINK}),
})
def llamada_llm(state: EstadoRag) -> dict:
    log_event("rag_node", node="llamada_llm", request_id=state["request_id"])
    # El estado conserva el id incluso si el ejecutor del grafo cambia de hilo.
    token = request_id_context.set(state["request_id"])
    try:
        return {"respuesta": llamar_llm(state["prompt"], branch="rag",
                                       schema=rag_response_schema(state["fragmentos"], state["pregunta"]), system=RAG_SYSTEM)}
    finally:
        request_id_context.reset(token)


@trace_node("respuesta")
def respuesta(state: EstadoRag) -> dict:
    log_event("rag_node", node="respuesta", request_id=state["request_id"])
    # No atribuir hechos a un documento que el recuperador no entregó.
    return {"respuesta": validate_rag_answer(state["respuesta"], state["fragmentos"], state["pregunta"])}


builder = StateGraph(EstadoRag)
builder.add_node("retrieval", retrieval)
builder.add_node("prompt", prompt)
builder.add_node("llamada_llm", llamada_llm)
builder.add_node("respuesta", respuesta)
builder.add_edge(START, "retrieval")
builder.add_edge("retrieval", "prompt")
builder.add_edge("prompt", "llamada_llm")
builder.add_edge("llamada_llm", "respuesta")
builder.add_edge("respuesta", END)
grafo = builder.compile()


if __name__ == "__main__":
    import argparse
    from pathlib import Path
    from uuid import uuid4

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("patient_id", type=int)
    parser.add_argument("pregunta")
    parser.add_argument("--request-id", default=str(uuid4()))
    parser.add_argument("--output", required=True, help="Archivo JSON para guardar el estado final")
    args = parser.parse_args()
    from app.clinical import get_clinical_patient
    patient = get_clinical_patient(args.patient_id)
    state = grafo.invoke({"pregunta": args.pregunta, "patient_id": args.patient_id, "patient_name": patient["name"],
                          "request_id": args.request_id})
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Estado final guardado en {output}")
