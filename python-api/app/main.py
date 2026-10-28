from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse
from opentelemetry.trace import StatusCode
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import Base, engine, get_db
from app.models import Patient
from app.metrics import install_metrics
from app.observability import install_request_logging
from app.schemas import ChatIn, PatientIn, PatientOut
from app.tracing import configure_tracing, tracer
from app.llm import LLMUnavailable, llamar_llm
from app.knowledge import EmbeddingUnavailable, QdrantUnavailable
from grafo import grafo


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Al arrancar crea public.patients si todavía no existe (no borra datos)
    Base.metadata.create_all(engine)
    tracing_provider = configure_tracing()
    try:
        yield
    finally:
        tracing_provider.shutdown()


# Las trazas de esta práctica cubren solo el RAG; FastAPI 0.162 trae spans HTTP propios.
app = FastAPI(title="python-api", lifespan=lifespan,
              telemetry={"tracing": False, "operation_spans": False})
install_metrics(app)
install_request_logging(app)

Db = Annotated[Session, Depends(get_db)]


@app.get("/", include_in_schema=False)
def chatbot_page():
    return FileResponse(Path(__file__).parent / "static" / "index.html")


@app.get("/health")
def health():
    # FastAPI convierte el dict a JSON y responde 200 por defecto
    return {"status": "ok"}


@app.post("/chat")
def chat(body: ChatIn, db: Db, request: Request):
    find_patient(body.patient_id, db)
    try:
        direct_answer = llamar_llm(body.question)
        with tracer.start_as_current_span("rag", attributes={
            "openinference.span.kind": "CHAIN", "request_id": request.state.request_id,
        }) as span:
            state = grafo.invoke({"pregunta": body.question, "patient_id": body.patient_id,
                                  "request_id": request.state.request_id})
            span.set_status(StatusCode.OK)
        return {"direct_answer": direct_answer, "rag_answer": state["respuesta"],
                "sources": state["fragmentos"]}
    except (LLMUnavailable, EmbeddingUnavailable, QdrantUnavailable) as error:
        raise HTTPException(status_code=503, detail=str(error)) from error


@app.post("/patients", response_model=PatientOut, status_code=201)
def create_patient(patient: PatientIn, db: Db):
    # Llega aquí solo si PatientIn validó los tres campos
    row = Patient(**patient.model_dump())
    db.add(row)
    db.commit()  # aquí SQLAlchemy envía el INSERT a PostgreSQL
    db.refresh(row)  # trae el id que generó la base
    return row


@app.get("/patients", response_model=list[PatientOut])
def list_patients(db: Db):
    return db.scalars(select(Patient).order_by(Patient.id)).all()


@app.get("/patients/{patient_id}", response_model=PatientOut)
def get_patient(patient_id: int, db: Db):
    return find_patient(patient_id, db)


@app.put("/patients/{patient_id}", response_model=PatientOut)
def update_patient(patient_id: int, patient: PatientIn, db: Db):
    # PUT reemplaza los tres campos; usa las mismas validaciones que POST.
    row = find_patient(patient_id, db)
    row.name = patient.name
    row.birth_date = patient.birth_date
    row.email = patient.email
    db.commit()
    db.refresh(row)
    return row


@app.delete("/patients/{patient_id}", status_code=204, response_class=Response)
def delete_patient(patient_id: int, db: Db):
    row = find_patient(patient_id, db)
    db.delete(row)
    db.commit()
    return Response(status_code=204)


def find_patient(patient_id: int, db: Session) -> Patient:
    row = db.get(Patient, patient_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Paciente no encontrado")
    return row
