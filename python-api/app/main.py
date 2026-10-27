from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import Depends, FastAPI
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import Base, engine, get_db
from app.models import Patient
from app.schemas import PatientIn, PatientOut


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Al arrancar crea public.patients si todavía no existe (no borra datos)
    Base.metadata.create_all(engine)
    yield


app = FastAPI(title="python-api", lifespan=lifespan)

Db = Annotated[Session, Depends(get_db)]


@app.get("/health")
def health():
    # FastAPI convierte el dict a JSON y responde 200 por defecto
    return {"status": "ok"}


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
    return db.get(Patient, patient_id)
