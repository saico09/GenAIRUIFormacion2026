"""Ensaya la recuperación SQL con una interrupción TCP aislada, sin parar PostgreSQL.

Desde PowerShell: Get-Content -Raw scripts/verificar_arranque_db.py |
    docker compose run --rm --no-deps -T python-api python -
Solo altera conexiones del contenedor de prueba; conserva las tablas y sus datos.
"""

import json
import select
import socket
import threading
import time
from contextlib import contextmanager
from datetime import datetime, timezone

from sqlalchemy import create_engine, text

from app import db, models  # Registra el mismo modelo que usa FastAPI.


@contextmanager
def delayed_postgres(available_after):
    """Acepta TCP sin contestar al inicio; luego deja pasar nuevas conexiones SQL."""
    stop = threading.Event()
    started = time.monotonic()
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen()
    listener.settimeout(0.2)
    connections = []
    accepted = []

    def serve(client):
        connections.append(client)
        if time.monotonic() - started < available_after:
            # La primera conexión queda sin respuesta, aunque después vuelva la ruta.
            stop.wait(60)
            client.close()
            return
        try:
            upstream = socket.create_connection(
                (db.DATABASE_URL.host, db.DATABASE_URL.port or 5432), timeout=5
            )
            connections.append(upstream)
            with client, upstream:
                while not stop.is_set():
                    readable, _, _ = select.select([client, upstream], [], [], 0.2)
                    for source in readable:
                        data = source.recv(65536)
                        if not data:
                            return
                        target = upstream if source is client else client
                        target.sendall(data)
        except OSError:
            client.close()

    def accept():
        while not stop.is_set():
            try:
                client, _ = listener.accept()
            except socket.timeout:
                continue
            except OSError:
                return
            accepted.append(round(time.monotonic() - started, 3))
            threading.Thread(target=serve, args=(client,), daemon=True).start()

    worker = threading.Thread(target=accept, daemon=True)
    worker.start()
    try:
        yield listener.getsockname()[1], accepted
    finally:
        stop.set()
        listener.close()
        worker.join(timeout=1)
        for connection in connections:
            connection.close()


def run_case(name, available_after, timeout_seconds, expect_success):
    original_engine = db.engine
    with delayed_postgres(available_after) as (port, accepted):
        test_engine = create_engine(
            db.DATABASE_URL.set(host="127.0.0.1", port=port),
            pool_pre_ping=True,
            connect_args={"connect_timeout": 5},
        )
        db.engine = test_engine
        started = time.monotonic()
        result = {"case": name, "timeout_seconds": timeout_seconds}
        try:
            db.initialize_database(timeout_seconds=timeout_seconds)
            with test_engine.connect() as connection:
                assert connection.execute(text("SELECT 1")).scalar_one() == 1
            result["success"] = True
        except Exception as error:
            # Nunca registrar el texto de una excepción que pueda contener credenciales.
            result.update(success=False, error_type=type(error).__name__)
        finally:
            result["elapsed_seconds"] = round(time.monotonic() - started, 3)
            result["connection_attempts_seconds"] = list(accepted)
            test_engine.dispose()
            db.engine = original_engine
    assert result["success"] == expect_success, result
    assert len(accepted) >= 2, "El ensayo debe provocar al menos un reintento real"
    if expect_success:
        assert available_after <= result["elapsed_seconds"] < timeout_seconds + 6, result
    else:
        assert timeout_seconds - 1 <= result["elapsed_seconds"] <= timeout_seconds + 6, result
    return result


results = [
    run_case("ruta_recuperada_mismo_proceso", 12, 40, True),
    run_case("ruta_sin_respuesta_plazo_acotado", 999, 12, False),
]
print(json.dumps({
    "checked_at": datetime.now(timezone.utc).isoformat(),
    "cases": results,
    "scope": "Proxy TCP efímero; PostgreSQL y Qdrant siguen funcionando.",
}, ensure_ascii=False, indent=2))
