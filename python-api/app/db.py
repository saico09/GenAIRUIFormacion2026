import os
from time import monotonic, sleep

from sqlalchemy import URL, create_engine, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.observability import log_event
from app.transaction_log import SCHEMA_LOCK

CONNECT_TIMEOUT_SECONDS = 5
STARTUP_RETRY_SECONDS = 2

# Los datos de conexión llegan como variables de entorno desde compose.yml (que las lee del .env)
DATABASE_URL = URL.create(
    "postgresql+psycopg",
    username=os.environ["POSTGRES_USER"],
    password=os.environ["POSTGRES_PASSWORD"],
    host=os.environ["POSTGRES_HOST"],
    port=int(os.environ.get("POSTGRES_PORT", "5432")),
    database=os.environ["POSTGRES_DB"],
)

# Descarta conexiones antiguas si PostgreSQL se reinicia mientras la API sigue viva.
engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,
    connect_args={"connect_timeout": CONNECT_TIMEOUT_SECONDS},
)
SessionLocal = sessionmaker(bind=engine)


class Base(DeclarativeBase):
    pass


def initialize_database(*, timeout_seconds: float = 120) -> None:
    """Inicializa sin borrar datos y tolera una conexión transitoriamente caída.

    No inicia otro intento después del plazo. Una conexión ya iniciada puede
    añadir hasta 5 s (un host); este plazo no limita la duración de consultas DDL.
    Los reintentos se restringen al arranque, nunca a las escrituras del CRUD.
    """
    if timeout_seconds <= 0:
        raise ValueError("El plazo de inicialización debe ser positivo.")

    started = monotonic()
    deadline = started + timeout_seconds
    attempts = 0
    while True:
        if attempts and monotonic() >= deadline:
            log_event("db_startup", status="failed", reason="deadline",
                      attempts=attempts, elapsed_seconds=round(monotonic() - started, 3))
            raise RuntimeError(
                f"PostgreSQL no estuvo disponible durante el plazo de {timeout_seconds:g} s."
            ) from None

        attempts += 1
        try:
            # La misma conexión comprueba el esquema y lo crea si falta. En
            # PostgreSQL, un fallo revierte esta transacción antes de reintentar.
            with engine.begin() as connection:
                # Ambas APIs comparten transaction_logs: serializa su primer DDL.
                connection.execute(text("SELECT pg_advisory_xact_lock(:lock)"), {"lock": SCHEMA_LOCK})
                Base.metadata.create_all(connection)
        except OperationalError as error:
            sqlstate = getattr(error.orig, "sqlstate", None)
            transient = (sqlstate is None or sqlstate.startswith("08")
                         or sqlstate in {"57P01", "57P02", "57P03"})
            if not transient:
                log_event("db_startup", status="failed", reason="permanent",
                          attempts=attempts, sqlstate=sqlstate,
                          error_type=type(error.orig).__name__)
                raise RuntimeError(
                    f"No se pudo inicializar PostgreSQL: error permanente (SQLSTATE {sqlstate})."
                ) from None

            remaining = deadline - monotonic()
            if remaining > 0:
                log_event("db_startup", status="waiting", attempts=attempts,
                          elapsed_seconds=round(monotonic() - started, 3),
                          error_type=type(error.orig).__name__, sqlstate=sqlstate)
                sleep(min(STARTUP_RETRY_SECONDS, remaining))
        else:
            log_event("db_startup", status="ready", attempts=attempts,
                      elapsed_seconds=round(monotonic() - started, 3))
            return


def get_db():
    # Una sesión por request; se cierra siempre al terminar
    with SessionLocal() as session:
        yield session
