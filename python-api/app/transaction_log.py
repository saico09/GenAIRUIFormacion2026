"""Persistencia del registro HTTP, separada de la transacción de negocio."""

from datetime import datetime, timezone
from uuid import uuid4

BODY_LIMIT = 128 * 1024
SCHEMA_LOCK = 71420261107  # Misma llave que Java al crear la tabla compartida.


class BodyCapture:
    """Conserva sólo el prefijo; el middleware entrega el cuerpo completo a su destino."""

    def __init__(self):
        self.data = bytearray()
        self.truncated = False

    def add(self, chunk: bytes) -> None:
        remaining = BODY_LIMIT - len(self.data)
        self.data.extend(chunk[:remaining])
        self.truncated = self.truncated or len(chunk) > remaining

    def text(self) -> str:
        # PostgreSQL TEXT no admite NUL; deja visible el carácter inválido.
        return self.data.decode("utf-8", errors="replace").replace("\x00", "\\u0000")


def write_transaction(values: dict) -> None:
    # Importación diferida: db usa log_event durante su inicialización.
    from app.db import SessionLocal
    from app.models import TransactionLog

    with SessionLocal() as session:
        session.add(TransactionLog(id=uuid4(), created_at=datetime.now(timezone.utc), **values))
        session.commit()
