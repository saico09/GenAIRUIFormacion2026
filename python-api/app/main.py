from contextlib import asynccontextmanager
from typing import Annotated
from uuid import UUID

from fastapi import Depends, FastAPI, HTTPException, Request, Response
from opentelemetry.trace import StatusCode
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db, initialize_database
from app.models import Patient
from app.metrics import install_metrics
from app.observability import install_request_logging
from app.schemas import ChatIn, ClinicalProposalIn, DiseaseIn, DiseaseOut, PatientIn, PatientOut
from app import clinical_store
from app.tracing import configure_tracing, tracer
from app.llm import CHAT_MODEL, LLMUnavailable, llamar_llm
from app.knowledge import EmbeddingUnavailable, QdrantUnavailable
from app.ui import install_ui
from app.clinical import (ClinicalPatientMissing, ClinicalUnavailable, ConsultationConflict,
                          get_clinical_patient, get_consultation, save_consultation, sync_history)
from app.clinical_proposals import propose_entries
from grafo import grafo
from rag import DIRECT_SYSTEM


@asynccontextmanager
async def lifespan(app: FastAPI):
    clinical_store.require_shared_history()
    # Al arrancar crea public.patients si todavía no existe (no borra datos)
    initialize_database()
    clinical_store.bootstrap_histories()
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
install_ui(app)

Db = Annotated[Session, Depends(get_db)]


@app.get("/health")
def health():
    clinical_store.require_shared_history()
    # FastAPI convierte el dict a JSON y responde 200 por defecto
    return {"status": "ok"}


@app.post("/chat")
def chat(body: ChatIn, request: Request):
    try:
        patient = get_clinical_patient(body.patient_id)
        execution_id = request.state.execution_id
        existing = get_consultation(body.patient_id, execution_id, body.question)
        if existing is not None:
            return consultation_result(body.patient_id, existing)
        direct_answer = llamar_llm(body.question, system=DIRECT_SYSTEM)
        with tracer.start_as_current_span("rag", attributes={
            "openinference.span.kind": "CHAIN", "request_id": request.state.request_id,
        }) as span:
            state = grafo.invoke({"pregunta": body.question, "patient_id": body.patient_id, "patient_name": patient["name"],
                                  "request_id": request.state.request_id})
            span.set_status(StatusCode.OK)
        result = {"direct_answer": direct_answer, "rag_answer": state["respuesta"], "sources": state["fragmentos"]}
        saved = save_consultation(body.patient_id, execution_id, body.question, result, CHAT_MODEL)
        return consultation_result(body.patient_id, saved)
    except ConsultationConflict as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    except ClinicalPatientMissing as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except (LLMUnavailable, EmbeddingUnavailable, QdrantUnavailable, ClinicalUnavailable, ValueError) as error:
        raise HTTPException(status_code=503, detail=str(error)) from error


def consultation_result(patient_id: int, saved: dict) -> dict:
    result = {key: saved[key] for key in ("direct_answer", "rag_answer", "sources", "model")}
    result["consultation"] = {"id": saved["id"], "patient_id": patient_id,
                              "created_at": saved["created_at"], "saved": True}
    try:
        sync_history(patient_id)
        result["index_synced"] = True
    except (ClinicalUnavailable, ClinicalPatientMissing, EmbeddingUnavailable, QdrantUnavailable, ValueError):
        result["index_synced"] = False
        result["warning"] = "La consulta quedó guardada en el informe y PostgreSQL. El índice RAG está pendiente; puedes reintentar su sincronización."
    return result


@app.post("/clinical/proposals")
def clinical_proposal(body: ClinicalProposalIn):
    try:
        return propose_entries(body.patient_id, body.note)
    except ClinicalPatientMissing as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except (ClinicalUnavailable, LLMUnavailable) as error:
        raise HTTPException(status_code=503, detail=str(error)) from error


@app.post("/clinical/patients/{patient_id}/sync")
def sync_clinical_history(patient_id: int):
    if patient_id < 1:
        raise HTTPException(status_code=422, detail="El ID debe ser positivo")
    try:
        return sync_history(patient_id, allow_missing=True)
    except (ClinicalUnavailable, EmbeddingUnavailable, QdrantUnavailable, ValueError) as error:
        raise HTTPException(status_code=503, detail="No se pudo actualizar el índice; la historia confirmada se conserva en Java") from error


@app.post("/patients", response_model=PatientOut, status_code=201)
def create_patient(patient: PatientIn, db: Db):
    return clinical_store.create_patient(db, patient)


@app.get("/patients", response_model=list[PatientOut])
def list_patients(db: Db):
    return db.scalars(select(Patient).order_by(Patient.id)).all()


@app.get("/patients/{patient_id}", response_model=PatientOut)
def get_patient(patient_id: int, db: Db):
    return find_patient(patient_id, db)


@app.put("/patients/{patient_id}", response_model=PatientOut)
def update_patient(patient_id: int, patient: PatientIn, db: Db):
    return clinical_store.update_patient(db, patient_id, patient)


@app.delete("/patients/{patient_id}", status_code=204, response_class=Response)
def delete_patient(patient_id: int, db: Db):
    clinical_store.delete_patient(db, patient_id)
    return Response(status_code=204)


@app.get("/patients/{patient_id}/diseases", response_model=list[DiseaseOut])
def list_diseases(patient_id: int, db: Db):
    return clinical_store.diseases(db, patient_id)


@app.get("/patients/{patient_id}/diseases/{disease_id}", response_model=DiseaseOut)
def get_disease(patient_id: int, disease_id: UUID, db: Db):
    row = clinical_store.diseases(db, patient_id, disease_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Registro no encontrado para este paciente")
    return row


@app.post("/patients/{patient_id}/diseases", response_model=DiseaseOut, status_code=201)
def create_disease(patient_id: int, body: DiseaseIn, db: Db):
    return clinical_store.mutate_disease(db, patient_id, body)


@app.put("/patients/{patient_id}/diseases/{disease_id}", response_model=DiseaseOut)
def update_disease(patient_id: int, disease_id: UUID, body: DiseaseIn, db: Db):
    return clinical_store.mutate_disease(db, patient_id, body, disease_id)


@app.delete("/patients/{patient_id}/diseases/{disease_id}", status_code=204, response_class=Response)
def delete_disease(patient_id: int, disease_id: UUID, db: Db):
    clinical_store.mutate_disease(db, patient_id, None, disease_id)
    return Response(status_code=204)


def find_patient(patient_id: int, db: Session) -> Patient:
    row = db.get(Patient, patient_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Paciente no encontrado")
    return row
