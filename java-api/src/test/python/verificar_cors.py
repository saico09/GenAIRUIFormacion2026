"""Comprueba CORS y CRUD real sin dependencias ni cambios en pacientes previos.

python java-api/src/test/python/verificar_cors.py --base-url http://127.0.0.1:8080
Para una lista personalizada, repetir --origin por cada origen autorizado.
"""

import argparse
import json
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from uuid import uuid4


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8080")
    parser.add_argument("--origin", action="append")
    parser.add_argument("--skip-request-id", action="store_true",
                        help="Copias S4-S6 sin filtro de logs: no exigir valor X-Request-ID")
    args = parser.parse_args()
    base_url = args.base_url.rstrip("/")
    origins = args.origin or ["http://localhost:8000", "http://127.0.0.1:8000"]
    checks = []

    def request(method, path, *, origin=None, payload=None, headers=None):
        supplied = dict(headers or {})
        if origin is not None:
            supplied["Origin"] = origin
        data = None
        if payload is not None:
            data = json.dumps(payload).encode("utf-8")
            supplied["Content-Type"] = "application/json"
        req = Request(base_url + path, data=data, headers=supplied, method=method)
        try:
            response = urlopen(req, timeout=15)
        except HTTPError as error:
            response = error
        with response:
            return response.status, response.headers, response.read()

    def expect(status, expected, label):
        assert status == expected, f"{label}: esperado {expected}, obtenido {status}"
        checks.append(label)

    def cors(headers, origin):
        assert headers.get("Access-Control-Allow-Origin") == origin, "El origen no se autoriza exactamente"
        assert headers.get("Access-Control-Allow-Credentials") is None, "No deben habilitarse credenciales"

    def snapshot():
        status, _, body = request("GET", "/patients")
        assert status == 200, "No se pudo leer el estado de pacientes"
        return json.loads(body)

    before = snapshot()
    previous_ids = {patient["id"] for patient in before}
    created_ids = set()
    created_id = None
    try:
        for origin in origins:
            for method in ("GET", "POST", "PUT", "DELETE"):
                path = "/patients" if method in ("GET", "POST") else "/patients/999999"
                status, headers, _ = request("OPTIONS", path, origin=origin, headers={
                    "Access-Control-Request-Method": method,
                    "Access-Control-Request-Headers": "Content-Type, X-Request-ID",
                })
                expect(status, 200, f"preflight {method} {origin}")
                cors(headers, origin)
                assert method in {value.strip() for value in headers.get("Access-Control-Allow-Methods", "").split(",")}
                allowed_headers = {value.strip().lower() for value in headers.get("Access-Control-Allow-Headers", "").split(",")}
                assert {"content-type", "x-request-id"} <= allowed_headers

            request_id = "cors-" + uuid4().hex
            status, headers, _ = request("GET", "/patients", origin=origin,
                                         headers={"X-Request-ID": request_id})
            expect(status, 200, f"GET autorizado {origin}")
            cors(headers, origin)
            if not args.skip_request_id:
                assert headers.get("X-Request-ID") == request_id
            assert "x-request-id" in {value.strip().lower() for value in headers.get("Access-Control-Expose-Headers", "").split(",")}

        rejected = "https://cors-no-autorizado.invalid"
        for method in ("GET", "OPTIONS"):
            extra = {"Access-Control-Request-Method": "POST"} if method == "OPTIONS" else None
            status, headers, _ = request(method, "/patients", origin=rejected, headers=extra)
            expect(status, 403, f"{method} origen rechazado")
            assert headers.get("Access-Control-Allow-Origin") is None

        status, _, _ = request("OPTIONS", "/patients", origin=origins[0], headers={
            "Access-Control-Request-Method": "POST", "Access-Control-Request-Headers": "Authorization",
        })
        expect(status, 403, "preflight cabecera no autorizada")

        origin = origins[0]
        original = {"name": "CORS Demo", "birth_date": "1995-05-05", "email": "cors@example.com"}
        edited = {"name": "CORS Editado", "birth_date": "1996-06-06", "email": "cors-editado@example.com"}
        status, headers, body = request("POST", "/patients", origin=origin, payload=original)
        created = json.loads(body)
        # Registrar el id antes de las aserciones asegura limpieza si falla un header.
        if status == 201 and isinstance(created, dict):
            created_id = created.get("id")
            if isinstance(created_id, int) and created_id not in previous_ids:
                created_ids.add(created_id)
        expect(status, 201, "POST CRUD")
        cors(headers, origin)
        assert created_id in created_ids and created == {"id": created_id, **original}
        path = f"/patients/{created_id}"

        status, headers, body = request("GET", path, origin=origin)
        expect(status, 200, "GET CRUD")
        cors(headers, origin)
        assert json.loads(body) == created

        status, headers, body = request("PUT", path, origin=origin, payload=edited)
        expect(status, 200, "PUT CRUD")
        cors(headers, origin)
        assert json.loads(body) == {"id": created_id, **edited}

        for method, target in (("POST", "/patients"), ("PUT", path)):
            status, headers, body = request(method, target, origin=origin, payload={**edited, "name": ""})
            if method == "POST" and status == 201:
                unexpected_id = json.loads(body).get("id")
                if isinstance(unexpected_id, int) and unexpected_id not in previous_ids:
                    created_ids.add(unexpected_id)
            expect(status, 422, f"{method} validacion")
            cors(headers, origin)
        assert snapshot() == before + [{"id": created_id, **edited}], "Las validaciones cambiaron filas"

        status, headers, body = request("DELETE", path, origin=origin)
        expect(status, 204, "DELETE CRUD")
        created_ids.discard(created_id)
        cors(headers, origin)
        assert body == b"", "DELETE204 debe quedar sin cuerpo"
        status, headers, _ = request("GET", path, origin=origin)
        expect(status, 404, "GET eliminado")
        cors(headers, origin)
    finally:
        for temporary_id in created_ids:
            status, _, _ = request("DELETE", f"/patients/{temporary_id}")
            assert status in (204, 404), "No se pudo limpiar el paciente de prueba"
        assert snapshot() == before, "Los pacientes previos no se conservaron"

    print(json.dumps({"result": "passed", "base_url": base_url, "origins": origins,
                      "request_id_value_checked": not args.skip_request_id,
                      "checks": checks, "previous_patients_preserved": len(before),
                      "temporary_patient_remaining": False}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
