"""Sonda de conexión: JSONL sin conninfo, contraseñas ni payload de autenticación.

Usa POSTGRES_HOST/PORT/USER/PASSWORD/DB. Cada ronda abre cuatro conexiones
nuevas en paralelo. No ejecuta SQL ni modifica PostgreSQL. --hold mantiene
el proceso vivo al terminar para observar/reanudar el pod de diagnóstico.
"""

import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import json
import os
import select
import socket
import struct
import threading
import time

import psycopg
from psycopg import pq
from psycopg.conninfo import make_conninfo


TIMEOUT = 5.0
PRINT_LOCK = threading.Lock()


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def emit(event, **values):
    with PRINT_LOCK:
        print(json.dumps({"event": event, "utc": utc_now(),
                          "monotonic": time.monotonic(), **values}), flush=True)


def local_address(fd):
    """Consulta el socket prestado; detach evita cerrar el descriptor de libpq."""
    borrowed = None
    try:
        borrowed = socket.socket(fileno=fd)
        return list(borrowed.getsockname())
    except OSError:
        return None
    finally:
        if borrowed is not None:
            borrowed.detach()


def probe_raw(name, config, deadline):
    family, address = config["endpoint"]
    packet = config["startup"] if name == "startup_raw" else struct.pack("!II", 8, 80877103)
    result = {}
    with socket.socket(family, socket.SOCK_STREAM) as connection:
        try:
            connection.settimeout(max(0.001, deadline - time.monotonic()))
            connected_at = time.monotonic()
            connection.connect(address)
            result["tcp_connect_ms"] = round((time.monotonic() - connected_at) * 1000, 3)
            result["local_address"] = list(connection.getsockname())
            connection.settimeout(max(0.001, deadline - time.monotonic()))
            sent_at = time.monotonic()
            connection.sendall(packet)
            connection.settimeout(max(0.001, deadline - time.monotonic()))
            first = connection.recv(1)
            result["first_byte_ms_after_send"] = round((time.monotonic() - sent_at) * 1000, 3)
            # Se conserva únicamente el tipo de mensaje, nunca su contenido.
            result["first_byte"] = first.decode("ascii") if first in (b"N", b"S", b"R", b"E") else ("eof" if not first else "other")
            expected = (b"R", b"E") if name == "startup_raw" else (b"N",)
            result["result"] = "protocol_response" if first in expected else "unexpected_response"
        except Exception as error:
            result.update(result="timeout" if isinstance(error, TimeoutError) else "error",
                          error_type=type(error).__name__)
            if isinstance(getattr(error, "errno", None), int):
                result["errno"] = error.errno
    return result


def probe_libpq(name, config, deadline, round_number, started):
    options = dict(config["params"])
    if name == "libpq_disable":
        options.update(sslmode="disable", gssencmode="disable")
    connection = None
    result = {"states": []}
    last = None
    try:
        # PQconnectPoll ignora connect_timeout: el plazo se controla aquí.
        connection = pq.PGconn.connect_start(make_conninfo(**options).encode())
        while True:
            if time.monotonic() >= deadline:
                result["result"] = "timeout"
                break
            poll = pq.PollingStatus(connection.connect_poll())
            status = pq.ConnStatus(connection.status)
            state = (status.name, poll.name)
            if state != last:
                transition = {"status": status.name, "poll": poll.name,
                              "elapsed_ms": round((time.monotonic() - started) * 1000, 3)}
                result["states"].append(transition)
                emit("libpq_state", round=round_number, probe=name, **transition)
                last = state
            if connection.socket >= 0:
                result["local_address"] = local_address(connection.socket)
            if poll == pq.PollingStatus.OK:
                result.update(result="connection_ready", ssl_in_use=connection.ssl_in_use,
                              used_gssapi=connection.used_gssapi)
                break
            if poll == pq.PollingStatus.FAILED:
                result["result"] = "connection_failed"
                break
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                result["result"] = "timeout"
                break
            if poll == pq.PollingStatus.READING:
                select.select([connection.socket], [], [], remaining)
            elif poll == pq.PollingStatus.WRITING:
                select.select([], [connection.socket], [], remaining)
            else:
                time.sleep(min(0.001, remaining))
    except Exception as error:
        result.update(result="error", error_type=type(error).__name__)
    finally:
        if connection is not None:
            connection.finish()
    return result


def run_probe(name, config, barrier, round_number):
    barrier.wait(timeout=10)
    started = time.monotonic()
    emit("probe_start", round=round_number, probe=name)
    if name in ("sslrequest", "startup_raw"):
        result = probe_raw(name, config, started + TIMEOUT)
    else:
        result = probe_libpq(name, config, started + TIMEOUT, round_number, started)
    emit("probe_result", round=round_number, probe=name,
         elapsed_ms=round((time.monotonic() - started) * 1000, 3), **result)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default=os.environ.get("POSTGRES_HOST"))
    parser.add_argument("--rounds", type=int, default=5)
    parser.add_argument("--hold", action="store_true")
    args = parser.parse_args()
    required = ("POSTGRES_USER", "POSTGRES_PASSWORD", "POSTGRES_DB")
    missing = [key for key in required if key not in os.environ]
    if missing or not args.host or args.rounds < 1:
        emit("configuration_error", missing_variables=missing,
             missing_host=not bool(args.host), invalid_rounds=args.rounds < 1)
        return 2
    port = int(os.environ.get("POSTGRES_PORT", "5432"))
    addresses = socket.getaddrinfo(args.host, port, type=socket.SOCK_STREAM)
    # Resolvemos antes de la barrera; las cuatro pruebas usan el mismo destino.
    address = next((item for item in addresses if item[0] == socket.AF_INET), addresses[0])
    family, _, _, _, endpoint = address
    params = {"host": args.host, "hostaddr": endpoint[0], "port": port,
              "user": os.environ["POSTGRES_USER"], "password": os.environ["POSTGRES_PASSWORD"],
              "dbname": os.environ["POSTGRES_DB"]}
    body = struct.pack("!I", 196608) + b"user\0" + params["user"].encode() + b"\0database\0" + params["dbname"].encode() + b"\0\0"
    config = {"params": params, "endpoint": (family, endpoint),
              "startup": struct.pack("!I", len(body) + 4) + body}
    emit("run_start", host=args.host, resolved_address=list(endpoint), rounds=args.rounds,
         timeout_seconds=TIMEOUT, interval_seconds=2, psycopg=psycopg.__version__,
         libpq_runtime=pq.version(), libpq_build=pq.__build_version__, implementation=pq.__impl__)
    for round_number in range(1, args.rounds + 1):
        barrier = threading.Barrier(4)
        with ThreadPoolExecutor(max_workers=4) as executor:
            futures = [executor.submit(run_probe, name, config, barrier, round_number)
                       for name in ("sslrequest", "startup_raw", "libpq_default", "libpq_disable")]
            for future in futures:
                future.result()
        if round_number < args.rounds:
            time.sleep(2)
    emit("run_complete", rounds=args.rounds, hold=args.hold)
    if args.hold:
        while True:
            time.sleep(60)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        raise SystemExit(130)
    except Exception as error:
        # El error completo de libpq puede incluir datos de conexión.
        emit("fatal", error_type=type(error).__name__)
        raise SystemExit(1) from None
