"""Comprueba el CRUD por HTTP y conserva los pacientes que ya existían.

Uso: python scripts/verificar_crud.py --base-url http://localhost:8000
Solo requiere la biblioteca estándar de Python.
"""

import argparse
import json
import sys
from urllib.error import HTTPError
from urllib.request import Request, urlopen


ORIGINAL = {
    "name": "Test Demo",
    "birth_date": "1995-05-05",
    "email": "test@example.com",
}
EDITADO = {
    "name": "Test Editado",
    "birth_date": "1996-06-06",
    "email": "editado@example.com",
}
ID_AUSENTE = 999999


def comprobar(condition, message):
    if not condition:
        raise AssertionError(message)


def request(base_url, method, path, expected, payload=None):
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    headers = {"Content-Type": "application/json"} if data is not None else {}
    req = Request(base_url + path, data=data, headers=headers, method=method)
    try:
        response = urlopen(req, timeout=15)
    except HTTPError as error:
        response = error
    with response:
        status = response.status
        body = response.read()
    comprobar(status == expected, f"{method} {path}: esperado {expected}, obtenido {status}")
    print(f"OK {method} {path} -> {status}")
    if expected == 204:
        comprobar(body == b"", "DELETE 204 debe devolver un cuerpo vacío")
        return None
    return json.loads(body)


def pacientes(base_url):
    rows = request(base_url, "GET", "/patients", 200)
    comprobar(isinstance(rows, list), "GET /patients debe devolver una lista")
    by_id = {row["id"]: row for row in rows}
    comprobar(len(by_id) == len(rows), "La lista contiene IDs duplicados")
    return by_id


def verificar(base_url):
    initial = pacientes(base_url)
    comprobar(ID_AUSENTE not in initial, "999999 existe: elige otro ID antes de ejecutar esta prueba")
    created_id = None
    try:
        # Los errores sobre un ID ausente no deben cambiar los datos guardados.
        missing_path = f"/patients/{ID_AUSENTE}"
        request(base_url, "GET", missing_path, 404)
        request(base_url, "PUT", missing_path, 404, EDITADO)
        request(base_url, "DELETE", missing_path, 404)
        comprobar(pacientes(base_url) == initial, "Una operación sobre un ID ausente cambió filas")

        created = request(base_url, "POST", "/patients", 201, ORIGINAL)
        patient_id = created["id"]
        comprobar(type(patient_id) is int and patient_id not in initial, "POST no generó un ID nuevo")
        created_id = patient_id
        path = f"/patients/{created_id}"
        expected_created = {"id": created_id, **ORIGINAL}
        comprobar(created == expected_created, "POST no devolvió los cuatro campos esperados")
        comprobar(pacientes(base_url) == {**initial, created_id: expected_created}, "El listado tras POST no coincide")
        comprobar(request(base_url, "GET", path, 200) == expected_created, "GET no coincide con POST")

        edited = request(base_url, "PUT", path, 200, EDITADO)
        expected_edited = {"id": created_id, **EDITADO}
        comprobar(edited == expected_edited, "PUT no reemplazó los tres campos")
        comprobar(request(base_url, "GET", path, 200) == expected_edited, "GET no muestra los tres cambios de PUT")
        expected_rows = {**initial, created_id: expected_edited}
        comprobar(pacientes(base_url) == expected_rows, "PUT modificó otras filas")

        # Cada campo inválido se prueba por separado en ambas operaciones.
        for field, bad_value in (("name", "   "), ("birth_date", "2026-02-30"), ("email", "sin-arroba")):
            invalid = {**ORIGINAL, field: bad_value}
            for method, target in (("POST", "/patients"), ("PUT", path)):
                request(base_url, method, target, 422, invalid)
                comprobar(pacientes(base_url) == expected_rows, f"{method} con {field} inválido cambió filas")
                print(f"OK {method}: {field} inválido no cambia filas")

        request(base_url, "DELETE", path, 204)
        created_id = None
        request(base_url, "GET", path, 404)
        comprobar(pacientes(base_url) == initial, "Los pacientes originales no quedaron intactos")
        print(f"OK CRUD completo; {len(initial)} pacientes previos conservados, sin paciente de prueba")
    finally:
        # Si algo falla, solo se intenta borrar el ID creado por esta ejecución.
        if created_id is not None:
            try:
                request(base_url, "DELETE", f"/patients/{created_id}", 204)
                print(f"Limpieza: eliminado paciente de prueba {created_id}")
            except Exception as error:
                print(f"Limpieza pendiente para paciente de prueba {created_id}: {error}", file=sys.stderr)


def main():
    parser = argparse.ArgumentParser(description="Verifica CRUD y validaciones sin borrar pacientes previos.")
    parser.add_argument("--base-url", default="http://localhost:8000", help="URL de la API (sin /patients)")
    args = parser.parse_args()
    try:
        verificar(args.base_url.rstrip("/"))
    except (AssertionError, KeyError, ValueError, OSError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
